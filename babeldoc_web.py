import streamlit as st
import subprocess
import tempfile
import os
from pathlib import Path
import time
import threading
import queue
import zipfile
import io
import re
import uuid

# 加载.env文件
try:
    load_dotenv()
except:
    pass

# 自定义CSS样式
st.markdown("""
<style>
/* 交换按钮样式 - 更大的按钮 */
.swap-button-container {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100%;
    padding-top: 1.5rem;
}

/* 调整交换按钮大小 */
.swap-button-container .stButton > button {
    font-size: 1.5rem !important;
    padding: 0.5rem 1rem !important;
    height: 3rem !important;
    line-height: 1.5 !important;
    min-height: 3rem !important;
}

/* 调整按钮本身的样式 */
.stButton > button {
    margin: 0 auto;
    display: block;
}

/* 移除各种边框 */
div[data-testid="stSelectbox"] > div,
div[data-testid="stFileUploader"],
div[data-testid="stFileUploader"] > div,
div[data-testid="stFileUploader"] section,
div[data-testid="stFileUploader"] section > div {
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
}

.stButton button {
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
}

/* 下载按钮样式 */
.download-buttons {
    background-color: #e8f5e8;
    padding: 10px;
    border-radius: 5px;
    margin-top: 15px;
}

/* 文件列表样式 */
.file-item {
    background-color: #f8f9fa;
    padding: 8px;
    border-radius: 4px;
    margin: 4px 0;
    border-left: 3px solid #28a745;
}
</style>
""", unsafe_allow_html=True)

# 预设的大模型服务商配置
MODEL_PROVIDERS = {
    "SiliconFlow": {
        "api_key_env": "SILICONFLOW_API_KEY",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "THUDM/GLM-4-9B-0414"
    },
    "智谱": {
        "api_key_env": "ZHIPU_API_KEY", 
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "GLM-4-Flash-250414"
    },         
    "ModelScope": {
        "api_key_env": "MODELSCOPE_API_KEY", 
        "base_url": "https://api-inference.modelscope.cn/v1",
        "model": "Qwen/Qwen2.5-72B-Instruct"
    },
    "OpenRouter": {
        "api_key_env": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1", 
        "model": "google/gemini-2.0-flash-exp:free"
    },
    "OpenAI": {
        "api_key_env": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-3.5-turbo"
    },
    "自定义": {
        "api_key_env": "CUSTOM_API_KEY",
        "base_url": "",
        "model": ""
    }
}

@st.cache_data
def get_api_key_for_provider(provider_name):
    """根据服务商获取对应的API Key（缓存版本）"""
    if provider_name not in MODEL_PROVIDERS:
        return ""
    
    env_var = MODEL_PROVIDERS[provider_name]["api_key_env"]
    
    # 从环境变量读取
    api_key = os.environ.get(env_var)
    if api_key:
        return api_key
    
    # 尝试从Streamlit secrets读取
    try:
        if hasattr(st, 'secrets'):
            api_key = st.secrets.get(env_var, "")
            if api_key:
                return api_key
    except:
        pass
    
    return ""

def analyze_progress_from_output(line):
    """根据输出内容分析当前进度"""
    line_lower = line.lower()
    
    # 进度关键词映射
    progress_patterns = [
        (r'saving|saved|writing', 95),
        (r'generating|creating.*pdf', 85),
        (r'translating.*page|translation.*complete', 70),
        (r'translate.*text|processing.*translation', 50),
        (r'extracting.*text|parsing.*pdf|reading.*pdf', 25),
        (r'loading|initializing|starting', 15),
        (r'error|failed|exception', -1)  # 错误情况
    ]
    
    for pattern, progress in progress_patterns:
        if re.search(pattern, line_lower):
            return progress
    
    # 如果包含百分比数字，尝试提取
    percent_match = re.search(r'(\d+)%', line)
    if percent_match:
        return int(percent_match.group(1))
    
    return None

def run_translation_with_queue(cmd, output_queue):
    """运行翻译命令，通过队列传递输出"""
    try:
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True,
            universal_newlines=True,
            bufsize=1
        )
        
        stdout_lines = []
        stderr_lines = []
        
        def read_stream(stream, lines_list, is_stderr=False):
            try:
                for line in iter(stream.readline, ''):
                    if line:
                        line = line.rstrip()
                        lines_list.append(line)
                        # 分析进度
                        progress = analyze_progress_from_output(line)
                        output_queue.put(('output', line, is_stderr, progress))
            except Exception as e:
                output_queue.put(('error', f"读取输出流错误: {str(e)}", False, None))
        
        stdout_thread = threading.Thread(target=read_stream, args=(process.stdout, stdout_lines, False))
        stderr_thread = threading.Thread(target=read_stream, args=(process.stderr, stderr_lines, True))
        
        stdout_thread.start()
        stderr_thread.start()
        
        returncode = process.wait()
        
        stdout_thread.join()
        stderr_thread.join()
        
        output_queue.put(('done', returncode, None, None))
        
        return returncode, '\n'.join(stdout_lines), '\n'.join(stderr_lines)
        
    except Exception as e:
        output_queue.put(('error', f"执行命令错误: {str(e)}", None, None))
        return -1, "", str(e)

def get_file_stem(filename):
    """从文件名获取不带扩展名的部分"""
    return Path(filename).stem

def find_and_read_output_files(output_path, original_filename):
    """查找并读取输出文件到内存"""
    output_files = []
    if not os.path.exists(output_path):
        return output_files
    
    file_stem = get_file_stem(original_filename)
    search_patterns = [
        "*_translated*.pdf",
        f"*{file_stem}*.pdf",
        f"{file_stem}_*.pdf", 
        "*dual*.pdf",
        "*mono*.pdf",
        "*.pdf"  # 最后搜索所有PDF
    ]
    
    try:
        found_files = []
        for pattern in search_patterns:
            found_files.extend(list(Path(output_path).glob(pattern)))
        
        # 去重并按修改时间排序（最新的在前）
        found_files = list(set(found_files))
        found_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        # 读取文件到内存
        for file_path in found_files:
            if file_path.exists():
                try:
                    with open(file_path, 'rb') as f:
                        file_data = f.read()
                    
                    output_files.append({
                        'original_name': original_filename,
                        'translated_name': file_path.name,
                        'file_data': file_data,
                        'size': len(file_data)
                    })
                except Exception as e:
                    print(f"读取文件失败: {e}")
        
    except Exception:
        pass
    
    return output_files

def create_download_zip(files):
    """创建包含多个文件的ZIP"""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file_info in files:
            zip_file.writestr(file_info['translated_name'], file_info['file_data'])
    zip_buffer.seek(0)
    return zip_buffer.getvalue()

def calculate_unified_progress(completed_files, total_files, current_file_progress):
    """计算统一进度"""
    if total_files == 0:
        return 0
    
    base_progress = completed_files / total_files
    current_contribution = (current_file_progress / 100) / total_files
    
    return min((base_progress + current_contribution) * 100, 100)

def display_download_section(results):
    """显示下载区域"""
    if not results:
        return
    
    st.markdown('<div class="download-buttons">', unsafe_allow_html=True)
    st.markdown("📥 **下载翻译结果:**")
    
    # 单个文件下载
    for i, result in enumerate(results):
        col1, col2 = st.columns([3, 1])
        
        with col1:
            file_size_mb = result['size'] / (1024 * 1024)
            st.markdown(f'<div class="file-item">📄 {result["translated_name"]} ({file_size_mb:.1f} MB)</div>', 
                       unsafe_allow_html=True)
        
        with col2:
            st.download_button(
                label="下载",
                data=result['file_data'],
                file_name=result['translated_name'],
                mime="application/pdf",
                key=f"download_{result['translated_name']}_{i}_{int(time.time())}"
            )
    
    # 批量下载
    if len(results) > 1:
        try:
            zip_data = create_download_zip(results)
            
            st.download_button(
                label="📦 下载所有文件 (ZIP)",
                data=zip_data,
                file_name=f"translated_pdfs_{int(time.time())}.zip",
                mime="application/zip",
                key=f"download_all_zip_{int(time.time())}"
            )
        except Exception as e:
            st.error(f"创建ZIP文件失败: {e}")
    
    st.markdown('</div>', unsafe_allow_html=True)

# 初始化会话状态
if 'translation_results' not in st.session_state:
    st.session_state.translation_results = []

# 显示应用标题
st.markdown(
    """
    <h1 style='text-align: center;'>📚 PDF翻译</h1>
    """,
    unsafe_allow_html=True
)

# 文件上传
uploaded_files = st.file_uploader(
    "上传PDF文件", 
    type=['pdf'], 
    accept_multiple_files=True
)

# 开始翻译按钮
start_button = st.button("🚀 开始翻译", type="primary", disabled=not uploaded_files)

# 如果点击了翻译按钮，立即清空缓存
if start_button:
    st.session_state.translation_results = []

# 立即预留进度显示位置
progress_placeholder = st.empty()

# 语言设置
with st.expander("🌍 语言设置", expanded=True):
    languages = {
        "zh": "中文", "en": "英语", "ja": "日语", "ko": "韩语",
        "fr": "法语", "de": "德语", "pt": "葡萄牙语", "es": "西班牙语",
        "ru": "俄语", "it": "意大利语", "nl": "荷兰语", "ar": "阿拉伯语"
    }

    lang_codes = list(languages.keys())
    col_in, col_swap, col_out = st.columns([5, 1.5, 5])
    
    with col_in:
        if 'lang_in_idx' not in st.session_state:
            st.session_state.lang_in_idx = 0
        
        lang_in_idx = st.selectbox(
            "源语言", 
            range(len(lang_codes)), 
            index=st.session_state.lang_in_idx,
            format_func=lambda x: f"{languages[lang_codes[x]]} ({lang_codes[x]})",
            key="lang_in_select"
        )
        st.session_state.lang_in_idx = lang_in_idx
        lang_in = lang_codes[lang_in_idx]
    
    with col_swap:
        st.markdown('<div class="swap-button-container">', unsafe_allow_html=True)
        if st.button("⇄", help="交换语言", key="swap_lang", use_container_width=True):
            temp_idx = st.session_state.lang_in_idx
            st.session_state.lang_in_idx = st.session_state.get('lang_out_idx', 1)
            st.session_state.lang_out_idx = temp_idx
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col_out:
        if 'lang_out_idx' not in st.session_state:
            st.session_state.lang_out_idx = 1
        
        lang_out_idx = st.selectbox(
            "目标语言", 
            range(len(lang_codes)), 
            index=st.session_state.lang_out_idx,
            format_func=lambda x: f"{languages[lang_codes[x]]} ({lang_codes[x]})",
            key="lang_out_select"
        )
        st.session_state.lang_out_idx = lang_out_idx
        lang_out = lang_codes[lang_out_idx]

# 大模型设置
with st.expander("🤖 大模型设置"):
    use_openai = st.checkbox("使用大模型翻译", value=True)
    
    if use_openai:
        provider_names = list(MODEL_PROVIDERS.keys())
        selected_provider = st.selectbox(
            "选择服务商",
            provider_names,
            index=0,
            help="选择预设的大模型服务商，或选择'自定义'手动配置"
        )
        
        provider_config = MODEL_PROVIDERS[selected_provider]
        col7, col8 = st.columns(2)
        
        with col7:
            if selected_provider == "自定义":
                openai_base_url = st.text_input("API Base URL", 
                    value="", help="自定义API的基础URL")
            else:
                openai_base_url = st.text_input("API Base URL", 
                    value=provider_config["base_url"],
                    help=f"{selected_provider} API的基础URL", disabled=True)
            
            openai_model = st.text_input("模型名称", 
                value=provider_config["model"],
                placeholder=f"推荐: {provider_config['model']}",
                help=f"{selected_provider} 推荐模型，可修改为其他模型")
            
        with col8:
            auto_key = get_api_key_for_provider(selected_provider)
            openai_key = st.text_input("API Key", 
                value=auto_key, type="password",
                help=f"输入 {selected_provider} 的API密钥")
            custom_prompt = st.text_area("自定义提示词", 
                placeholder="可选：自定义翻译提示词", help="自定义系统提示词")
        
        if selected_provider != "自定义":
            if openai_model == provider_config["model"]:
                st.info(f"📌 当前使用: **{selected_provider}** | 模型: `{openai_model}` (推荐)")
            else:
                st.info(f"📌 当前使用: **{selected_provider}** | 模型: `{openai_model}` (自定义)")

# 输出选项 - 将页码范围移到这里
with st.expander("📄 输出选项"):
    col3, col4 = st.columns(2)
    
    with col3:
        pages = st.text_input("页面范围", "", placeholder="例: 1-5,8,10-", 
                             help="指定要翻译的页面，留空则翻译全部页面")
        watermark_mode = st.selectbox("水印模式", 
            ["watermarked", "no_watermark", "both"], index=1,
            format_func=lambda x: {"watermarked": "添加水印", "no_watermark": "无水印", "both": "两种版本"}[x])
        
    with col4:
        no_dual = st.checkbox("不输出双语版", help="不生成原文+译文对照版本")
        no_mono = st.checkbox("不输出单语版", value=True, help="不生成纯翻译版本")
        only_translated = st.checkbox("仅包含翻译页面", help="输出PDF中只包含翻译的页面")

# 文档处理选项
with st.expander("⚙️ 文档处理选项"):
    col5, col6 = st.columns(2)
    
    with col5:
        skip_scanned = st.checkbox("跳过扫描检测", value=True, 
            help="跳过扫描文档检测(加快非扫描文档处理)")
        split_short_lines = st.checkbox("强制分割短行", value=True,
            help="将短行强制分为不同段落")
        translate_table = st.checkbox("翻译表格文字", help="实验性功能")
        
    with col6:
        short_line_factor = st.number_input("短行分割阈值", 
            value=0.8, min_value=0.1, max_value=5.0, step=0.1, help="短行分割的阈值因子")
        qps = st.slider("翻译速度限制 (QPS)", 1, 20, 3, 
            help="每秒查询数限制，默认3，过高可能被限流")
        skip_clean = st.checkbox("跳过PDF清理", help="跳过PDF清理步骤")

# 高级选项
with st.expander("🔧 高级选项"):
    col9, col10 = st.columns(2)
    
    with col9:
        enhance_compatibility = st.checkbox("增强兼容性", help="启用所有兼容性增强选项")
        disable_rich_text = st.checkbox("禁用富文本翻译", help="可能有助于改善某些PDF的兼容性")
        dual_translate_first = st.checkbox("双语版中译文优先", help="在双语PDF中将翻译页面放在前面")
        
    with col10:
        ocr_workaround = st.checkbox("OCR解决方案", help="添加文本填充背景(实验性)")
        auto_ocr = st.checkbox("自动启用OCR", help="自动检测并启用OCR处理")
        max_pages_per_part = st.number_input("每部分最大页数", 
            value=0, min_value=0, max_value=1000, help="分割翻译的每部分最大页数，0表示不分割")

# 显示之前的下载结果（只在没有开始新翻译时显示）
if st.session_state.translation_results and not start_button:
    st.markdown("---")
    display_download_section(st.session_state.translation_results)

# 翻译处理逻辑
if start_button:
    if use_openai and not openai_key:
        with progress_placeholder.container():
            st.error("❌ 请输入API Key")
        st.stop()
    
    # 在占位符中显示进度
    with progress_placeholder.container():
        st.markdown("---")
        
        # 统一进度显示
        with st.expander("📊 翻译进度", expanded=True):
            progress_bar = st.progress(0)
            status_text = st.empty()
            download_placeholder = st.empty()
        
        total_files = len(uploaded_files)
        successful_files = 0
        
        for i, uploaded_file in enumerate(uploaded_files):
            file_num = i + 1
            
            # 为每个文件创建独立的临时目录
            with tempfile.TemporaryDirectory() as temp_output_dir:
                # 初始化当前文件状态
                if total_files == 1:
                    status_text.text(f"准备翻译: {uploaded_file.name}")
                else:
                    status_text.text(f"文件 {file_num}/{total_files}: {uploaded_file.name} - 准备中...")
                
                with tempfile.TemporaryDirectory() as temp_input_dir:
                    temp_path = Path(temp_input_dir)
                    file_path = temp_path / uploaded_file.name
                    
                    try:
                        with open(file_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                    except Exception as e:
                        st.error(f"❌ 保存文件失败: {e}")
                        continue
                    
                    # 更新进度：文件保存完成
                    current_file_progress = 10
                    unified_progress = calculate_unified_progress(i, total_files, current_file_progress)
                    progress_bar.progress(unified_progress / 100)
                    
                    if total_files == 1:
                        status_text.text(f"构建翻译命令... ({current_file_progress}%)")
                    else:
                        status_text.text(f"文件 {file_num}/{total_files}: {uploaded_file.name} - 构建翻译命令... ({current_file_progress}%)")
                    
                    # 构建命令 - 使用临时输出目录
                    cmd = [
                        "babeldoc", "--files", str(file_path),
                        "--lang-in", lang_in, "--lang-out", lang_out,
                        "--output", temp_output_dir,  # 使用临时目录
                        "--watermark-output-mode", watermark_mode,
                        "--qps", str(qps)
                    ]
                    
                    # 添加参数
                    if pages: cmd.extend(["--pages", pages])
                    if no_dual: cmd.append("--no-dual")
                    if no_mono: cmd.append("--no-mono")
                    if only_translated: cmd.append("--only-include-translated-page")
                    if skip_scanned: cmd.append("--skip-scanned-detection")
                    if split_short_lines:
                        cmd.append("--split-short-lines")
                        cmd.extend(["--short-line-split-factor", str(short_line_factor)])
                    if translate_table: cmd.append("--translate-table-text")
                    if skip_clean: cmd.append("--skip-clean")
                    if enhance_compatibility: cmd.append("--enhance-compatibility")
                    if disable_rich_text: cmd.append("--disable-rich-text-translate")
                    if dual_translate_first: cmd.append("--dual-translate-first")
                    if ocr_workaround: cmd.append("--ocr-workaround")
                    if auto_ocr: cmd.append("--auto-enable-ocr-workaround")
                    if max_pages_per_part > 0: cmd.extend(["--max-pages-per-part", str(max_pages_per_part)])
                    
                    if use_openai and openai_key:
                        cmd.extend([
                            "--openai", "--openai-api-key", openai_key,
                            "--openai-model", openai_model, "--openai-base-url", openai_base_url
                        ])
                        if custom_prompt: cmd.extend(["--custom-system-prompt", custom_prompt])
                    
                    # 更新进度：开始翻译
                    current_file_progress = 15
                    unified_progress = calculate_unified_progress(i, total_files, current_file_progress)
                    progress_bar.progress(unified_progress / 100)
                    
                    if total_files == 1:
                        status_text.text(f"正在执行翻译... ({current_file_progress}%)")
                    else:
                        status_text.text(f"文件 {file_num}/{total_files}: {uploaded_file.name} - 正在执行翻译... ({current_file_progress}%)")
                    
                    start_time = time.time()
                    output_queue = queue.Queue()
                    
                    translate_thread = threading.Thread(
                        target=run_translation_with_queue, args=(cmd, output_queue))
                    translate_thread.start()
                    
                    # 实时进度监控
                    returncode = None
                    stderr = ""
                    last_progress_time = time.time()
                    
                    while True:
                        try:
                            msg = output_queue.get(timeout=0.1)
                            msg_type = msg[0]
                            
                            if msg_type == 'output':
                                line = msg[1]
                                is_stderr = msg[2]
                                detected_progress = msg[3]
                                
                                if is_stderr:
                                    stderr += line + "\n"
                                
                                # 根据输出更新进度
                                if detected_progress is not None and detected_progress > 0:
                                    # 确保进度只增不减
                                    if detected_progress > current_file_progress:
                                        current_file_progress = min(detected_progress, 95)
                                        unified_progress = calculate_unified_progress(i, total_files, current_file_progress)
                                        progress_bar.progress(unified_progress / 100)
                                        
                                        # 更新状态文本
                                        if current_file_progress < 30:
                                            stage = "📖 正在解析PDF文档..."
                                        elif current_file_progress < 70:
                                            stage = "🔤 正在翻译文本内容..."
                                        elif current_file_progress < 90:
                                            stage = "📝 正在生成翻译文档..."
                                        else:
                                            stage = "💾 正在保存文件..."
                                        
                                        if total_files == 1:
                                            status_text.text(f"{stage} ({current_file_progress}%)")
                                        else:
                                            status_text.text(f"文件 {file_num}/{total_files}: {uploaded_file.name} - {stage} ({current_file_progress}%)")
                            
                            elif msg_type == 'done':
                                returncode = msg[1]
                                break
                                
                            elif msg_type == 'error':
                                returncode = -1
                                break
                                
                        except queue.Empty:
                            # 超时处理 - 缓慢推进进度（避免卡住的感觉）
                            current_time = time.time()
                            if current_time - last_progress_time > 2 and current_file_progress < 85:
                                current_file_progress += 1
                                unified_progress = calculate_unified_progress(i, total_files, current_file_progress)
                                progress_bar.progress(unified_progress / 100)
                                last_progress_time = current_time
                            
                            # 检查超时（5分钟）
                            if current_time - start_time > 300:
                                returncode = -1
                                break
                    
                    translate_thread.join(timeout=5)
                    
                    # 查找并读取输出文件
                    current_file_progress = 90
                    unified_progress = calculate_unified_progress(i, total_files, current_file_progress)
                    progress_bar.progress(unified_progress / 100)
                    
                    if total_files == 1:
                        status_text.text(f"🔍 正在处理输出文件... ({current_file_progress}%)")
                    else:
                        status_text.text(f"文件 {file_num}/{total_files}: {uploaded_file.name} - 🔍 正在处理输出文件... ({current_file_progress}%)")
                    
                    output_files = find_and_read_output_files(temp_output_dir, uploaded_file.name)
                    
                    if returncode == 0 and output_files:
                        # 完成当前文件
                        current_file_progress = 100
                        unified_progress = calculate_unified_progress(i, total_files, current_file_progress)
                        progress_bar.progress(unified_progress / 100)
                        
                        if total_files == 1:
                            status_text.text("✅ 翻译完成")
                        else:
                            status_text.text(f"文件 {file_num}/{total_files}: {uploaded_file.name} - ✅ 翻译完成")
                        
                        successful_files += 1
                        
                        # 保存结果到session state（已读取到内存）
                        st.session_state.translation_results.extend(output_files)
                    else:
                        if total_files == 1:
                            status_text.text("❌ 翻译失败")
                        else:
                            status_text.text(f"文件 {file_num}/{total_files}: {uploaded_file.name} - ❌ 翻译失败")
                        
                        if stderr:
                            st.error(f"翻译错误: {stderr.strip()[-200:]}")  # 只显示最后200个字符
        
        # 完成所有文件处理
        progress_bar.progress(1.0)
        status_text.text(f"🎉 处理完成! 成功: {successful_files}/{total_files}")
        
        if successful_files > 0:
            st.balloons()
            
            # 在进度区域内显示下载按钮
            with download_placeholder.container():
                display_download_section(st.session_state.translation_results)
        else:
            st.error("❌ 没有文件成功翻译，请检查配置")

# 使用说明
with st.expander("📖 使用说明"):
    st.markdown("""
    **页面范围格式：**
    - `1,2,3` - 翻译第1、2、3页
    - `1-5` - 翻译第1到5页  
    - `1-` - 从第1页翻译到最后
    - `-3` - 翻译前3页
    - `1,3-5,8` - 组合使用
    
    **大模型服务商配置：**
    - **SiliconFlow**: 硅基流动，性价比高
    - **ModelScope**: 魔搭社区，阿里巴巴
    - **OpenRouter**: 多模型聚合平台  
    - **OpenAI**: 官方ChatGPT服务
    - **自定义**: 手动配置其他服务商
    
    **API Key配置：**
    - 支持在界面中直接输入


    **📲 如何在手机上像App一样使用？**
    
    **对于 iPhone (Safari 浏览器):**
    1. 点击屏幕底部的 **分享** 图标 (一个方框加一个向上的箭头)。
    2. 向下滚动，找到并点击 **“添加到主屏幕”** (Add to Home Screen)。
    3. 点击 **“添加”** (Add) 即可。

    **对于 Android (Chrome 浏览器):**
    1. 点击浏览器右上角的 **三个点** 菜单按钮。
    2. 找到并点击 **“安装应用”** (Install app) 或 **“添加到主屏幕”** (Add to Home screen)。
    3. 按照提示完成操作。   

    """)
