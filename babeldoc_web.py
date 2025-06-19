import streamlit as st
import subprocess
import tempfile
import os
from pathlib import Path
import time
#from dotenv import load_dotenv
import threading
import queue

# 设置无头环境变量（必须在导入matplotlib之前）
os.environ['MPLBACKEND'] = 'Agg'
os.environ['DISPLAY'] = ''

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

/* 语言选择容器 */
.language-selection-container {
    display: flex;
    align-items: center;
    gap: 1rem;
}

/* 进度条百分比样式 */
.progress-text {
    text-align: center;
    font-weight: bold;
    margin-bottom: 0.5rem;
}

/* 日志样式 */
.log-container {
    background-color: #f0f2f6;
    padding: 10px;
    border-radius: 5px;
    font-family: monospace;
    font-size: 12px;
    height: 200px;
    overflow-y: auto;
    border: 1px solid #ddd;
}

/* 移除语言选择框边框 */
div[data-testid="stSelectbox"] > div {
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
}

div[data-testid="stSelectbox"] > div > div {
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
}

div[data-testid="stSelectbox"] > div > div > div {
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
}

/* 移除文件上传区域边框 */
div[data-testid="stFileUploader"] {
    border: none !important;
    box-shadow: none !important;
}

div[data-testid="stFileUploader"] > div {
    border: none !important;
    box-shadow: none !important;
}

div[data-testid="stFileUploader"] section {
    border: none !important;
    box-shadow: none !important;
}

/* 移除文件上传的拖拽区域边框 */
div[data-testid="stFileUploader"] section > div {
    border: none !important;
    box-shadow: none !important;
}

/* 移除路径选择按钮的边框 */
.stButton button {
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
}

/* 确保中间列完全居中 */
.center-column {
    display: flex;
    justify-content: center;
    align-items: center;
    width: 100%;
}

/* 文件夹选择按钮对齐 */
.folder-button-align {
    margin-top: 1.65rem;
}

/* 云端部署提示样式 */
.cloud-info {
    background-color: #e7f3ff;
    border: 1px solid #b3d9ff;
    color: #0056b3;
    padding: 12px;
    border-radius: 5px;
    margin-bottom: 1rem;
}

/* 环境检查样式 */
.env-check {
    background-color: #f8f9fa;
    border: 1px solid #dee2e6;
    color: #495057;
    padding: 12px;
    border-radius: 5px;
    margin-bottom: 1rem;
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

def setup_headless_environment():
    """设置无头环境"""
    # 设置matplotlib为无头模式
    try:
        import matplotlib
        matplotlib.use('Agg')
    except ImportError:
        pass
    
    # 设置OpenCV为无头模式
    os.environ['OPENCV_IO_ENABLE_OPENEXR'] = '0'
    
    # 禁用GUI相关的环境变量
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    
    # 设置其他可能需要的环境变量
    os.environ['PYTHONUNBUFFERED'] = '1'

def get_api_key_for_provider(provider_name):
    """根据服务商获取对应的API Key"""
    if provider_name not in MODEL_PROVIDERS:
        return ""
    
    env_var = MODEL_PROVIDERS[provider_name]["api_key_env"]
    
    # 从环境变量读取
    api_key = os.environ.get(env_var)
    if api_key:
        return api_key
    
    # 尝试从Streamlit secrets读取
    try:
        import streamlit as st
        if hasattr(st, 'secrets'):
            api_key = st.secrets.get(env_var, "")
            if api_key:
                return api_key
    except:
        pass
    
    # 从用户配置目录读取（仅在非云端环境）
    try:
        config_paths = [
            Path.home() / '.config' / 'babeldoc' / f'{env_var.lower()}.txt',
            Path.home() / f'.{env_var.lower()}',
            Path('.') / f'.{env_var.lower()}'
        ]
        
        for config_path in config_paths:
            if config_path.exists():
                try:
                    return config_path.read_text().strip()
                except:
                    pass
    except:
        pass
    
    return ""

def is_cloud_environment():
    """检测是否在云端环境运行"""
    cloud_indicators = [
        'STREAMLIT_SHARING_MODE',
        'STREAMLIT_SERVER_PORT', 
        'STREAMLIT_CLOUD',
        'HEROKU_APP_NAME',
        'RAILWAY_ENVIRONMENT',
        'VERCEL',
        'CODESPACE_NAME',
        'GITPOD_WORKSPACE_ID'
    ]
    
    for indicator in cloud_indicators:
        if os.environ.get(indicator):
            return True
    
    # 检查服务器地址
    server_address = os.environ.get('STREAMLIT_SERVER_ADDRESS', '')
    if any(cloud_domain in server_address for cloud_domain in ['streamlit.io', 'herokuapp.com', 'railway.app']):
        return True
    
    return False

def get_default_output_path():
    """获取默认输出路径"""
    if is_cloud_environment():
        # 云端环境使用临时目录
        return "/tmp/translate_output"
    else:
        # 本地环境使用当前目录下的子目录
        return os.path.join(os.getcwd(), "translate_output")

def check_system_dependencies():
    """检查系统依赖"""
    dependencies = {
        'babeldoc': 'babeldoc --version',
        'python': 'python --version',
        'pip': 'pip --version'
    }
    
    results = {}
    for name, cmd in dependencies.items():
        try:
            result = subprocess.run(cmd.split(), capture_output=True, text=True, timeout=5)
            results[name] = result.returncode == 0
        except:
            results[name] = False
    
    return results

def run_translation_with_queue(cmd, output_queue):
    """运行翻译命令，通过队列传递输出"""
    try:
        # 设置无头环境变量
        env = os.environ.copy()
        env.update({
            'MPLBACKEND': 'Agg',
            'DISPLAY': '',
            'QT_QPA_PLATFORM': 'offscreen',
            'OPENCV_IO_ENABLE_OPENEXR': '0',
            'PYTHONUNBUFFERED': '1'
        })
        
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True,
            universal_newlines=True,
            bufsize=1,  # 行缓冲
            env=env  # 使用修改后的环境变量
        )
        
        stdout_lines = []
        stderr_lines = []
        
        # 创建线程读取输出
        def read_stream(stream, lines_list, is_stderr=False):
            try:
                for line in iter(stream.readline, ''):
                    if line:
                        line = line.rstrip()
                        lines_list.append(line)
                        # 将输出放入队列
                        output_queue.put(('output', line, is_stderr))
            except Exception as e:
                output_queue.put(('error', f"读取输出流错误: {str(e)}", is_stderr))
        
        stdout_thread = threading.Thread(target=read_stream, args=(process.stdout, stdout_lines, False))
        stderr_thread = threading.Thread(target=read_stream, args=(process.stderr, stderr_lines, True))
        
        stdout_thread.start()
        stderr_thread.start()
        
        # 等待进程结束
        returncode = process.wait()
        
        stdout_thread.join()
        stderr_thread.join()
        
        # 发送完成信号
        output_queue.put(('done', returncode, None))
        
        return returncode, '\n'.join(stdout_lines), '\n'.join(stderr_lines)
        
    except Exception as e:
        output_queue.put(('error', f"执行命令错误: {str(e)}", None))
        return -1, "", str(e)

def get_file_stem(filename):
    """从文件名获取不带扩展名的部分"""
    return Path(filename).stem

# 初始化无头环境
setup_headless_environment()

# 显示应用标题
st.markdown(
    """
    <h1 style='text-align: center;'>📚 PDF翻译</h1>
    """,
    unsafe_allow_html=True
)

# 检测运行环境并显示信息
is_cloud = is_cloud_environment()

# 环境检查
with st.expander("🔧 环境检查", expanded=False):
    if is_cloud:
        st.markdown("""
        <div class="cloud-info">
            <strong>☁️ 云端环境检测到</strong><br>
            应用正在云端环境中运行，已自动配置无头模式。<br>
            输出文件将保存到临时目录，请及时下载。
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="env-check">
            <strong>💻 本地环境检测到</strong><br>
            应用在本地环境中运行。
        </div>
        """, unsafe_allow_html=True)
    
    # 检查系统依赖
    deps = check_system_dependencies()
    for name, status in deps.items():
        status_icon = "✅" if status else "❌"
        st.write(f"{status_icon} {name}: {'可用' if status else '不可用'}")

# 文件上传
uploaded_files = st.file_uploader(
    "上传PDF文件", 
    type=['pdf'], 
    accept_multiple_files=True
)

# 开始翻译按钮
start_button = st.button("🚀 开始翻译", type="primary", disabled=not uploaded_files)

# 进度条占位符
progress_placeholder = st.empty()

# 语言设置 - 调整列宽和居中
with st.expander("🌍 语言设置", expanded=True):
    languages = {
        "zh": "中文",
        "en": "英语", 
        "ja": "日语",
        "ko": "韩语",
        "fr": "法语",
        "de": "德语", 
        "pt": "葡萄牙语",        
        "es": "西班牙语",
        "ru": "俄语",
        "it": "意大利语",
        "nl": "荷兰语",
        "ar": "阿拉伯语"
    }

    lang_codes = list(languages.keys())
    # 调整列宽比例，使中间列更窄
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
        # 使用新的居中容器
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
            # API Base URL - 自定义时可编辑，其他时固定
            if selected_provider == "自定义":
                openai_base_url = st.text_input("API Base URL", 
                    value="",
                    help="自定义API的基础URL"
                )
            else:
                openai_base_url = st.text_input("API Base URL", 
                    value=provider_config["base_url"],
                    help=f"{selected_provider} API的基础URL",
                    disabled=True
                )
            
            # 模型名称 - 始终可编辑，预填推荐值
            if selected_provider == "自定义":
                model_placeholder = "请输入模型名称"
                model_help = "自定义模型名称"
            else:
                model_placeholder = f"推荐: {provider_config['model']}"
                model_help = f"{selected_provider} 推荐模型，可修改为其他模型"
            
            openai_model = st.text_input("模型名称", 
                value=provider_config["model"],
                placeholder=model_placeholder,
                help=model_help
            )
            
        with col8:
            auto_key = get_api_key_for_provider(selected_provider)
            openai_key = st.text_input("API Key", 
                value=auto_key,
                type="password",
                help=f"输入 {selected_provider} 的API密钥"
            )
            custom_prompt = st.text_area("自定义提示词", 
                placeholder="可选：自定义翻译提示词",
                help="自定义系统提示词"
            )
        
        # 显示配置信息
        if selected_provider != "自定义":
            if openai_model == provider_config["model"]:
                st.info(f"📌 当前使用: **{selected_provider}** | 模型: `{openai_model}` (推荐)")
            else:
                st.info(f"📌 当前使用: **{selected_provider}** | 模型: `{openai_model}` (自定义)")

# 基本设置 - 修改输出路径处理
with st.expander("⚙️ 基本设置", expanded=True):
    col1, col2 = st.columns([1, 1])
    
    with col1:
        pages = st.text_input("页面范围", "", placeholder="例: 1-5,8,10-")
        
    with col2:
        # 初始化输出路径
        if 'output_path' not in st.session_state:
            st.session_state.output_path = get_default_output_path()
        
        output_path = st.text_input(
            "输出路径", 
            value=st.session_state.output_path,
            help="翻译后的PDF文件保存路径",
            key="output_path_input"
        )
        
        # 提供路径建议
        col_suggest1, col_suggest2 = st.columns(2)
        with col_suggest1:
            if st.button("📁 使用临时目录", help="使用系统临时目录"):
                st.session_state.output_path = "/tmp/translate_output" if is_cloud else "./temp_translate"
                st.rerun()
        
        with col_suggest2:
            if st.button("🏠 使用当前目录", help="使用当前工作目录"):
                st.session_state.output_path = "./translate_output"
                st.rerun()

# 输出选项
with st.expander("📄 输出选项"):
    col3, col4 = st.columns(2)
    
    with col3:
        watermark_mode = st.selectbox("水印模式", 
            ["watermarked", "no_watermark", "both"],
            index=1,
            format_func=lambda x: {"watermarked": "添加水印", "no_watermark": "无水印", "both": "两种版本"}[x]
        )
        no_dual = st.checkbox("不输出双语版", help="不生成原文+译文对照版本")
        
    with col4:
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
            value=1.2, min_value=0.1, max_value=5.0, step=0.1,
            help="短行分割的阈值因子")
        qps = st.slider("翻译速度限制 (QPS)", 1, 20, 3, 
            help="每秒查询数限制，默认3，过高可能被限流")
        skip_clean = st.checkbox("跳过PDF清理", help="跳过PDF清理步骤")

# 高级选项
with st.expander("🔧 高级选项"):
    col9, col10 = st.columns(2)
    
    with col9:
        enhance_compatibility = st.checkbox("增强兼容性", 
            help="启用所有兼容性增强选项")
        disable_rich_text = st.checkbox("禁用富文本翻译",
            help="可能有助于改善某些PDF的兼容性")
        dual_translate_first = st.checkbox("双语版中译文优先",
            help="在双语PDF中将翻译页面放在前面")
        
    with col10:
        ocr_workaround = st.checkbox("OCR解决方案",
            help="添加文本填充背景(实验性)")
        auto_ocr = st.checkbox("自动启用OCR",
            help="自动检测并启用OCR处理")
        max_pages_per_part = st.number_input("每部分最大页数", 
            value=0, min_value=0, max_value=1000,
            help="分割翻译的每部分最大页数，0表示不分割")

# 翻译处理逻辑
if start_button:
    if use_openai and not openai_key:
        st.error("❌ 请输入API Key")
        st.stop()
    
    if not output_path:
        st.error("❌ 请设置输出路径")
        st.stop()
    
    try:
        os.makedirs(output_path, exist_ok=True)
        st.success(f"✅ 输出目录已创建: {output_path}")
    except Exception as e:
        st.error(f"❌ 创建输出目录失败: {e}")
        st.stop()
    
    with progress_placeholder.container():
        # 翻译进度 - 可折叠
        with st.expander("📊 翻译进度", expanded=True):
            # 整体进度显示
            overall_progress_text = st.empty()
            overall_progress = st.progress(0)
            overall_status = st.empty()
            
            st.markdown("---")
            
            # 当前文件进度显示
            current_progress_text = st.empty()
            current_progress = st.progress(0)
            current_status = st.empty()
        
        # 实时日志显示 - 显示我们的进度信息
        with st.expander("📝 实时日志", expanded=True):
            log_container_main = st.empty()
        
        all_logs = []
        total_files = len(uploaded_files)
        
        # 日志更新函数 - 用于实时显示进度
        def update_log(message):
            timestamp = time.strftime('%H:%M:%S')
            all_logs.append(f"[{timestamp}] {message}")
            # 显示最新的15条日志
            recent_logs = all_logs[-15:]
            log_text = "\n".join(recent_logs)
            log_container_main.code(log_text, language=None)
        
        # 成功处理的文件计数
        successful_files = 0
        
        # 保存所有文件的输出
        all_file_outputs = {}
        
        for i, uploaded_file in enumerate(uploaded_files):
            file_num = i + 1
            overall_percent = int((i / total_files) * 100)
            overall_progress_text.markdown(f'<div class="progress-text">整体进度: {overall_percent}% ({file_num}/{total_files})</div>', unsafe_allow_html=True)
            overall_progress.progress(i / total_files)
            overall_status.text(f"正在处理: {uploaded_file.name}")
            
            current_progress_text.markdown(f'<div class="progress-text">当前文件: 0%</div>', unsafe_allow_html=True)
            current_progress.progress(0)
            current_status.text("准备中...")
            
            update_log(f"═══════════════════════════════════════")
            update_log(f"🔄 开始处理文件 {file_num}/{total_files}: {uploaded_file.name}")
            
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                file_path = temp_path / uploaded_file.name
                
                # 保存文件
                try:
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    update_log("✅ 文件已保存到临时目录")
                except Exception as e:
                    update_log(f"❌ 保存文件失败: {e}")
                    continue
                
                current_progress_text.markdown(f'<div class="progress-text">当前文件: 10%</div>', unsafe_allow_html=True)
                current_progress.progress(0.1)
                current_status.text("构建翻译命令...")
                
                # 构建命令
                cmd = [
                    "babeldoc",
                    "--files", str(file_path),
                    "--lang-in", lang_in,
                    "--lang-out", lang_out,
                    "--output", output_path,
                    "--watermark-output-mode", watermark_mode,
                    "--qps", str(qps)
                ]
                
                # 添加参数
                if pages:
                    cmd.extend(["--pages", pages])
                if no_dual:
                    cmd.append("--no-dual")
                if no_mono:
                    cmd.append("--no-mono")
                if only_translated:
                    cmd.append("--only-include-translated-page")
                if skip_scanned:
                    cmd.append("--skip-scanned-detection")
                if split_short_lines:
                    cmd.append("--split-short-lines")
                    cmd.extend(["--short-line-split-factor", str(short_line_factor)])
                if translate_table:
                    cmd.append("--translate-table-text")
                if skip_clean:
                    cmd.append("--skip-clean")
                if enhance_compatibility:
                    cmd.append("--enhance-compatibility")
                if disable_rich_text:
                    cmd.append("--disable-rich-text-translate")
                if dual_translate_first:
                    cmd.append("--dual-translate-first")
                if ocr_workaround:
                    cmd.append("--ocr-workaround")
                if auto_ocr:
                    cmd.append("--auto-enable-ocr-workaround")
                if max_pages_per_part > 0:
                    cmd.extend(["--max-pages-per-part", str(max_pages_per_part)])
                
                if use_openai and openai_key:
                    cmd.extend([
                        "--openai",
                        "--openai-api-key", openai_key,
                        "--openai-model", openai_model,
                        "--openai-base-url", openai_base_url
                    ])
                    if custom_prompt:
                        cmd.extend(["--custom-system-prompt", custom_prompt])
                
                update_log("🚀 开始执行翻译命令...")
                update_log(f"📝 翻译配置: {lang_in} → {lang_out}")
                update_log(f"🤖 使用模型: {openai_model if use_openai else '本地模型'}")
                update_log(f"🔧 无头模式: {'已启用' if is_cloud else '未启用'}")
                
                current_progress_text.markdown(f'<div class="progress-text">当前文件: 20%</div>', unsafe_allow_html=True)
                current_progress.progress(0.2)
                current_status.text("执行翻译中...")
                
                # 记录开始时间
                start_time = time.time()
                update_log("⏳ 正在调用babeldoc进行翻译...")
                
                # 创建输出队列
                output_queue = queue.Queue()
                
                # 启动翻译线程
                translate_thread = threading.Thread(
                    target=run_translation_with_queue,
                    args=(cmd, output_queue)
                )
                translate_thread.start()
                
                # 模拟进度
                progress_steps = [
                    (0.3, "📖 正在解析PDF文档..."),
                    (0.5, "🔤 正在翻译文本内容..."),
                    (0.7, "📝 正在生成翻译文档...")
                ]
                
                current_step = 0
                returncode = None
                stdout = ""
                stderr = ""
                
                # 主循环处理队列消息
                max_wait_time = 300  # 最大等待时间5分钟
                wait_start = time.time()
                
                while True:
                    try:
                        # 非阻塞获取消息
                        msg = output_queue.get(timeout=0.1)
                        
                        if msg[0] == 'output':
                            # 处理输出
                            line = msg[1]
                            is_stderr = msg[2]
                            
                            if is_stderr:
                                stderr += line + "\n"
                            else:
                                stdout += line + "\n"
                        
                        elif msg[0] == 'done':
                            # 翻译完成
                            returncode = msg[1]
                            break
                            
                        elif msg[0] == 'error':
                            # 发生错误
                            error_msg = msg[1]
                            update_log(f"❌ 翻译过程出错: {error_msg}")
                            returncode = -1
                            break
                            
                    except queue.Empty:
                        # 检查超时
                        if time.time() - wait_start > max_wait_time:
                            update_log("⚠️ 翻译超时，强制退出")
                            returncode = -1
                            break
                        
                        # 队列为空，更新进度
                        if current_step < len(progress_steps):
                            progress, status_text = progress_steps[current_step]
                            current_progress_text.markdown(f'<div class="progress-text">当前文件: {int(progress*100)}%</div>', unsafe_allow_html=True)
                            current_progress.progress(progress)
                            update_log(status_text)
                            current_step += 1
                
                # 等待线程结束
                translate_thread.join(timeout=5)
                
                elapsed_time = time.time() - start_time
                update_log(f"⏱️ 翻译耗时: {elapsed_time:.1f}秒")
                
                # 保存完整输出
                all_file_outputs[uploaded_file.name] = {
                    'stdout': stdout,
                    'stderr': stderr,
                    'returncode': returncode
                }
                
                # 检查输出文件
                current_progress_text.markdown(f'<div class="progress-text">当前文件: 80%</div>', unsafe_allow_html=True)
                current_progress.progress(0.8)
                update_log("🔍 正在检查输出文件...")
                
                file_stem = get_file_stem(uploaded_file.name)
                output_files = []
                
                # 搜索输出文件
                try:
                    search_patterns = [
                        "*_translated*.pdf",
                        f"*{file_stem}*.pdf",
                        f"{file_stem}_*.pdf",
                        "*dual*.pdf",
                        "*mono*.pdf"
                    ]
                    
                    for pattern in search_patterns:
                        found_files = list(Path(output_path).glob(pattern))
                        output_files.extend(found_files)
                    
                    # 去重
                    output_files = list(set(output_files))
                except Exception as e:
                    update_log(f"⚠️ 搜索输出文件时出错: {e}")
                
                if returncode == 0:
                    if output_files:
                        current_progress_text.markdown(f'<div class="progress-text">当前文件: 100% ✅</div>', unsafe_allow_html=True)
                        current_progress.progress(1.0)
                        current_status.text("✅ 翻译完成")
                        successful_files += 1
                        
                        update_log(f"✅ 翻译成功完成!")
                        update_log(f"📁 输出文件: {[f.name for f in output_files]}")
                        update_log(f"📍 保存位置: {output_path}")
                        
                    else:
                        current_status.text("⚠️ 未找到输出文件")
                        update_log(f"⚠️ 翻译进程成功，但未找到输出文件")
                else:
                    current_status.text("❌ 翻译失败")
                    update_log(f"❌ 翻译失败! 返回码: {returncode}")
                    
                    if stderr:
                        error_lines = stderr.strip().split('\n')
                        for line in error_lines[-3:]:
                            if line.strip():
                                update_log(f"🚨 错误: {line.strip()}")
        
        # 完成所有文件
        update_log(f"═══════════════════════════════════════")
        final_percent = 100
        overall_progress_text.markdown(f'<div class="progress-text">整体进度: {final_percent}% ✅ 处理完成!</div>', unsafe_allow_html=True)
        overall_progress.progress(1.0)
        overall_status.text(f"🎉 处理完成! 成功: {successful_files}/{total_files}")
        current_progress_text.markdown("")
        current_status.text("")
        
        update_log(f"🎉 所有文件处理完成!")
        update_log(f"📊 成功率: {successful_files}/{total_files} ({int(successful_files/total_files*100) if total_files > 0 else 0}%)")
        update_log(f"📁 输出目录: {output_path}")
        
        if successful_files > 0:
            st.balloons()
            st.success(f"📁 翻译结果保存在: {output_path}")
            
            # 在云端环境提供额外提示
            if is_cloud:
                st.info("☁️ 云端环境提示: 翻译完成的文件保存在临时目录中，请及时下载。")
        else:
            st.error("❌ 没有文件成功翻译，请检查配置和日志")

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
    
    **云端部署配置：**
    - **环境变量方式**: 在部署平台设置环境变量
    - **Streamlit Secrets**: 在`.streamlit/secrets.toml`文件中配置
    - **输出路径**: 云端环境建议使用`/tmp/`开头的临时目录
    
    **必需文件：**
    - `requirements.txt`: Python依赖
    - `packages.txt`: 系统依赖（解决libGL.so.1问题）
    
    **requirements.txt示例：**
    ```
    streamlit
    python-dotenv
    babeldoc
    matplotlib-base
    opencv-python-headless
    ```
    
    **packages.txt示例：**
    ```
    libgl1-mesa-glx
    libglib2.0-0
    libsm6
    libxext6
    libxrender-dev
    libgomp1
    ```
    
    **API Key配置方式：**
    
    1. **环境变量：**
    ```bash
    SILICONFLOW_API_KEY=your_key_here
    MODELSCOPE_API_KEY=your_key_here  
    OPENROUTER_API_KEY=your_key_here
    OPENAI_API_KEY=your_key_here
    ```
    
    2. **Streamlit Secrets：**
    ```toml
    SILICONFLOW_API_KEY = "your_key_here"
    MODELSCOPE_API_KEY = "your_key_here"
    OPENROUTER_API_KEY = "your_key_here"
    OPENAI_API_KEY = "your_key_here"
    ```
    """)
