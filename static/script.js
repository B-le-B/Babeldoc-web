// static/script.js - 修复版本
document.addEventListener('DOMContentLoaded', () => {
    const MODEL_PROVIDERS = { 
        "SiliconFlow": { base_url: "https://api.siliconflow.cn/v1", model: "THUDM/GLM-4-9B-0414" }, 
        "ModelScope": { base_url: "https://api-inference.modelscope.cn/v1", model: "Qwen/Qwen2.5-72B-Instruct" }, 
        "OpenRouter": { base_url: "https://openrouter.ai/api/v1", model: "google/gemini-flash-1.5" }, 
        "OpenAI": { base_url: "https://api.openai.com/v1", model: "gpt-4o-mini" }, 
        "Custom": { base_url: "", model: "" } 
    };
    
    // 获取当前语言
    const currentLang = document.documentElement.lang || 'zh';
    const isZh = currentLang === 'zh';
    
    // 语言文本配置
    const texts = {
        translating: isZh ? '翻译中...' : 'Translating...',
        uploading: isZh ? '正在上传文件...' : 'Uploading files...',
        connectionLost: isZh ? '与服务器的连接已断开。' : 'Connection to server lost.',
        clientError: isZh ? '客户端错误' : 'Client Error',
        serverError: isZh ? '服务器错误' : 'Server Error',
        noTaskId: isZh ? '未能从服务器获取任务ID。' : 'Failed to get task ID from server.',
        errorDetails: isZh ? '错误详情' : 'Error Details',
        downloadAll: isZh ? '📦 下载所有文件 (ZIP)' : '📦 Download All (ZIP)',
        processing: isZh ? '处理中...' : 'Processing...',
        completed: isZh ? '完成' : 'Completed',
        failed: isZh ? '失败' : 'Failed'
    };
    
    // 获取DOM元素
    const form = document.getElementById('translate-form');
    const submitBtn = document.getElementById('submit-btn');
    const progressArea = document.getElementById('progress-area');
    const statusText = document.getElementById('status-text');
    const totalProgressBar = document.getElementById('total-progress-bar');
    const downloadArea = document.getElementById('download-area');
    const downloadLinksContainer = document.getElementById('download-links');
    const errorDisplay = document.getElementById('error-display');
    const useOpenAICheckbox = document.getElementById('use_openai');
    const openaiSettings = document.getElementById('openai-settings');
    const providerSelect = document.getElementById('provider_select');
    const baseUrlInput = document.getElementById('openai_base_url');
    const modelInput = document.getElementById('openai_model');
    const swapLangBtn = document.getElementById('swap-lang-btn');
    const langInSelect = document.getElementById('lang_in');
    const langOutSelect = document.getElementById('lang_out');
    const providerNameInput = document.getElementById('provider_name');
    const initialButtonText = submitBtn.textContent;

    // 确保语言切换链接不被阻止
    document.querySelectorAll('.lang-switcher a').forEach(link => {
        link.addEventListener('click', (e) => {
            console.log('Language switch clicked:', link.href);
        });
    });

    // 关键修复：提供商配置更新 - 模型名称始终可输入
    const updateProviderFields = () => {
        const provider = providerSelect.value;
        const config = MODEL_PROVIDERS[provider];
        providerNameInput.value = provider;
        
        if (config) {
            baseUrlInput.value = config.base_url;
            modelInput.value = config.model; // 设置默认值
            
            const isCustom = provider === "Custom";
            
            // 关键修复：模型名称始终可输入
            baseUrlInput.readOnly = !isCustom;
            modelInput.readOnly = false; // 改为始终可输入
            
            // 更新输入框样式
            if (isCustom) {
                baseUrlInput.style.backgroundColor = '#fff';
            } else {
                baseUrlInput.style.backgroundColor = '#f8f9fa';
            }
            // 模型名称始终为白色背景（可输入状态）
            modelInput.style.backgroundColor = '#fff';
        }
    };
    
    // 事件监听器
    useOpenAICheckbox.addEventListener('change', () => { 
        openaiSettings.style.display = useOpenAICheckbox.checked ? 'block' : 'none'; 
    });
    
    providerSelect.addEventListener('change', updateProviderFields);
    
    swapLangBtn.addEventListener('click', (e) => {
        e.preventDefault();
        const temp = langInSelect.value; 
        langInSelect.value = langOutSelect.value; 
        langOutSelect.value = temp;
        
        // 添加视觉反馈
        swapLangBtn.style.transform = 'rotate(180deg)';
        setTimeout(() => {
            swapLangBtn.style.transform = '';
        }, 200);
    });
    
    // 初始化
    updateProviderFields();

    // 表单提交处理
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // 调试：打印表单数据
        const formData = new FormData(form);
        console.log('Form data being sent:');
        for (let [key, value] of formData.entries()) {
            console.log(key, ':', value);
        }
        
        // 重置状态
        submitBtn.disabled = true;
        submitBtn.textContent = texts.translating;
        progressArea.style.display = 'block';
        totalProgressBar.value = 0;
        totalProgressBar.style.backgroundColor = '';
        errorDisplay.style.display = 'none';
        statusText.textContent = texts.uploading;
        downloadArea.style.display = 'none';
        downloadLinksContainer.innerHTML = '';
        
        // 滚动到进度区域
        progressArea.scrollIntoView({ behavior: 'smooth' });
        
        try {
            const response = await fetch('/translate', { 
                method: 'POST', 
                body: formData
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `${texts.serverError}: ${response.status}`);
            }
            
            const { task_id } = await response.json();
            if (!task_id) throw new Error(texts.noTaskId);

            // 建立事件流连接
            const eventSource = new EventSource(`/progress/${task_id}`);
            
            eventSource.onmessage = (event) => {
                try {
                    const { type, data } = JSON.parse(event.data);
                    const log = data.log || '';
                    
                    if (type === 'output') {
                        const progress = data.progress || 0;
                        totalProgressBar.value = progress;
                        statusText.textContent = `${texts.processing} ${Math.round(progress)}%`;
                        
                    } else if (type === 'error' || type === 'done') {
                        const icon = type === 'error' ? '❌' : '✅';
                        const status = type === 'error' ? texts.failed : texts.completed;
                        statusText.textContent = `${icon} ${status}`;
                        
                        if (type === 'error') {
                            errorDisplay.textContent = `${texts.errorDetails}: ${log}`;
                            errorDisplay.style.display = 'block';
                            totalProgressBar.style.backgroundColor = '#dc3545';
                        } else {
                            totalProgressBar.value = 100;
                            totalProgressBar.style.backgroundColor = '#28a745';
                        }
                        
                        // 处理下载文件
                        if (data.files && data.files.length > 0) {
                            downloadArea.style.display = 'block';
                            
                            data.files.forEach(file => {
                                const a = document.createElement('a');
                                a.href = file.url; 
                                a.textContent = `📄 ${file.name}`;
                                downloadLinksContainer.appendChild(a);
                            });
                            
                            // 如果有多个文件，添加ZIP下载链接
                            if (data.files.length > 1) {
                                const zipLink = document.createElement('a');
                                zipLink.href = `/download_zip/${task_id}`; 
                                zipLink.textContent = texts.downloadAll;
                                zipLink.style.marginTop = '0.5rem';
                                downloadLinksContainer.appendChild(zipLink);
                            }
                        }
                        
                        // 关闭连接并重置按钮
                        eventSource.close();
                        submitBtn.disabled = false;
                        submitBtn.textContent = initialButtonText;
                    }
                } catch (parseError) {
                    console.error('Error parsing event data:', parseError);
                }
            };
            
            eventSource.onerror = (error) => {
                console.error('EventSource error:', error);
                statusText.textContent = "❌ " + texts.connectionLost;
                errorDisplay.textContent = texts.connectionLost;
                errorDisplay.style.display = 'block';
                eventSource.close();
                submitBtn.disabled = false; 
                submitBtn.textContent = initialButtonText;
                totalProgressBar.style.backgroundColor = '#dc3545';
            };
            
        } catch (error) {
            console.error('Submit error:', error);
            statusText.textContent = `❌ ${texts.clientError}: ${error.message}`;
            errorDisplay.textContent = error.message; 
            errorDisplay.style.display = 'block';
            submitBtn.disabled = false; 
            submitBtn.textContent = initialButtonText;
            totalProgressBar.style.backgroundColor = '#dc3545';
        }
    });

    // 文件选择变化时的提示
    const filesInput = document.getElementById('files');
    filesInput.addEventListener('change', (e) => {
        const files = e.target.files;
        if (files.length > 0) {
            const fileNames = Array.from(files).map(f => f.name).join(', ');
            console.log('Selected files:', fileNames);
        }
    });
});