# app.py (已完成最终逻辑修复)

import os
import re
import uuid
import queue
import json
import shutil
import threading
import subprocess
import tempfile
from pathlib import Path
from flask import Flask, request, render_template, Response, send_from_directory, jsonify, session, send_file
from werkzeug.utils import secure_filename
import io

# --- 配置 ---
TEMP_BASE_DIR = Path(tempfile.gettempdir()) / "babeldoc_flask_tasks"
os.makedirs(TEMP_BASE_DIR, exist_ok=True)
app = Flask(__name__)
app.secret_key = os.urandom(24)
task_queues = {}
translations = {
    'zh': {"title": "📚 PDF 翻译", "all_configs": "所有配置", "start_button": "🚀 开始翻译", "upload_label": "上传PDF文件", "lang_settings": "🌍 语言设置", "source_lang": "源语言", "target_lang": "目标语言", "swap_lang": "交换语言", "model_settings": "🤖 大模型设置", "use_model": "使用大模型翻译", "provider": "服务商", "custom_provider": "自定义", "api_base_url": "API Base URL", "model_name": "模型名称", "api_key": "API 密钥", "custom_prompt": "自定义提示词", "output_options": "📄 输出选项", "page_range": "页面范围", "page_range_placeholder": "例: 1-5,8,10-", "watermark": "水印模式", "watermark_add": "添加水印", "watermark_none": "无水印", "watermark_both": "两种版本", "no_dual": "不输出双语版", "no_mono": "不输出单语版", "only_translated": "仅包含翻译页面", "processing_options": "⚙️ 文档处理选项", "skip_scanned": "跳过扫描检测", "split_short": "强制分割短行", "translate_table": "翻译表格文字", "split_threshold": "短行分割阈值", "qps": "翻译速度 (QPS)", "skip_clean": "跳过PDF清理", "advanced_options": "🔧 高级选项", "enhance_compat": "增强兼容性", "disable_rich_text": "禁用富文本翻译", "dual_first": "双语版中译文优先", "ocr_workaround": "OCR解决方案", "auto_ocr": "自动启用OCR", "max_pages": "每部分最大页数", "progress_title": "📊 翻译进度", "status_starting": "准备开始...", "log_title": "日志:", "download_title": "下载结果:", "download_all_zip": "📦 下载所有文件 (ZIP)"},
    'en': {"title": "📚 PDF Translator", "all_configs": "All Configurations", "start_button": "🚀 Start Translation", "upload_label": "Upload PDF Files", "lang_settings": "🌍 Language Settings", "source_lang": "Source Language", "target_lang": "Target Language", "swap_lang": "Swap Languages", "model_settings": "🤖 Large Model Settings", "use_model": "Use Large Model", "provider": "Provider", "custom_provider": "Custom", "api_base_url": "API Base URL", "model_name": "Model Name", "api_key": "API Key", "custom_prompt": "Custom Prompt", "output_options": "📄 Output Options", "page_range": "Page Range", "page_range_placeholder": "e.g., 1-5,8,10-", "watermark": "Watermark Mode", "watermark_add": "Add Watermark", "watermark_none": "No Watermark", "watermark_both": "Both Versions", "no_dual": "No bilingual version", "no_mono": "No monolingual version", "only_translated": "Only include translated pages", "processing_options": "⚙️ Document Processing", "skip_scanned": "Skip scanned detection", "split_short": "Force split short lines", "translate_table": "Translate table text", "split_threshold": "Short line split threshold", "qps": "Translation speed (QPS)", "skip_clean": "Skip PDF cleaning", "advanced_options": "🔧 Advanced Options", "enhance_compat": "Enhance compatibility", "disable_rich_text": "Disable rich text", "dual_first": "Translated first in bilingual", "ocr_workaround": "OCR solution", "auto_ocr": "Auto-enable OCR", "max_pages": "Max pages per part", "progress_title": "📊 Translation Progress", "status_starting": "Starting...", "log_title": "Logs:", "download_title": "Download Results:", "download_all_zip": "📦 Download All (ZIP)"}
}

# ===============================================================
# (核心修复) 将服务商配置移至后端，作为单一可信源
# ===============================================================
MODEL_PROVIDERS_CONFIG = {
    "SiliconFlow": {"base_url": "https://api.siliconflow.cn/v1", "model": "THUDM/GLM-4-9B-0414"},
    "ModelScope": {"base_url": "https://api-inference.modelscope.cn/v1", "model": "Qwen/Qwen2.5-72B-Instruct"},
    "OpenRouter": {"base_url": "https://openrouter.ai/api/v1", "model": "google/gemini-flash-1.5"},
    "OpenAI": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
}
# ===============================================================

def analyze_progress_from_output(line):
    line_lower=line.lower()
    patterns=[(r'saving|saved|writing',95),(r'generating|creating.*pdf',85),(r'translating.*page|translation.*complete',70),(r'translate.*text|processing.*translation',50),(r'extracting.*text|parsing.*pdf|reading.*pdf',25),(r'loading|initializing|starting',15),(r'error|failed|exception',-1)]
    for p,v in patterns:
        if re.search(p,line_lower):return v
    m=re.search(r'(\d+)%',line)
    return int(m.group(1)) if m else None

def build_command(form, file_path, output_dir):
    cmd = ["babeldoc", "--files", str(file_path), "--output", str(output_dir), "--lang-in", form.get('lang_in', 'en'), "--lang-out", form.get('lang_out', 'zh')]
    optional_args = {'watermark_mode': '--watermark-output-mode', 'qps': '--qps', 'short_line_factor': '--short-line-split-factor', 'max_pages_per_part': '--max-pages-per-part', 'pages': '--pages'}
    for form_key, cmd_flag in optional_args.items():
        if value := form.get(form_key): cmd.extend([cmd_flag, value])
    checkbox_flags = ['no_dual', 'no_mono', 'only_translated', 'skip_scanned', 'split_short_lines', 'translate_table', 'skip_clean', 'enhance_compatibility', 'disable_rich_text', 'dual_translate_first', 'ocr_workaround', 'auto_ocr']
    for flag in checkbox_flags:
        if form.get(flag) == 'on': cmd.append(f"--{flag.replace('_', '-')}")

    # ===============================================================
    # (核心修复) 重写大模型参数逻辑
    # ===============================================================
    if form.get('use_openai') == 'on' and form.get('openai_key'):
        cmd.append('--openai')
        cmd.extend(['--openai-api-key', form.get('openai_key')])
        
        provider_name = form.get('provider_name') # 从前端获取选择的服务商名称
        
        # 如果是预设的服务商，从后端的配置中获取URL和模型
        if provider_name in MODEL_PROVIDERS_CONFIG:
            config = MODEL_PROVIDERS_CONFIG[provider_name]
            cmd.extend(['--openai-base-url', config['base_url']])
            # 允许用户覆盖预设模型
            cmd.extend(['--openai-model', form.get('openai_model', config['model'])])
        else: # 如果是“自定义”或其他情况
            if model := form.get('openai_model'):
                cmd.extend(['--openai-model', model])
            if url := form.get('openai_base_url'):
                cmd.extend(['--openai-base-url', url])
        
        if prompt := form.get('custom_prompt'):
            cmd.extend(['--custom-system-prompt', prompt])
    # ===============================================================
            
    return cmd

def run_translation_task(task_id, form_data, files_to_process):
    output_queue=task_queues.get(task_id)
    if not output_queue: return
    task_dir,output_dir=TEMP_BASE_DIR/task_id,TEMP_BASE_DIR/task_id/"output"
    total_files,successful_files_count=len(files_to_process),0
    def calc_progress(completed,total,current):return min((completed/total)*100+(current/100)*(100/total),100)
    try:
        for i,file_info in enumerate(files_to_process):
            file_had_error,file_path,file_name=False,file_info["path"],file_info["name"]
            output_queue.put(('output',{'log':f"开始处理文件: {file_name}",'is_stderr':False,'progress':calc_progress(i,total_files,5)}))
            cmd=build_command(form_data,file_path,output_dir)
            print(f"任务 {task_id}: 正在执行命令 -> {' '.join(cmd)}")
            process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,universal_newlines=True,bufsize=1,encoding='utf-8',errors='replace')
            error_log = [] # 收集每个文件的错误日志
            for stream,is_stderr in[(process.stdout,False),(process.stderr,True)]:
                for line in iter(stream.readline,''):
                    if line:
                        line=line.rstrip()
                        if is_stderr: error_log.append(line) # 收集所有stderr输出
                        if is_stderr and any(kw in line.lower() for kw in['error','failed','invalid','exception','timeout']): file_had_error=True
                        progress=analyze_progress_from_output(line)or 0
                        log_data={'log':line,'is_stderr':is_stderr,'progress':calc_progress(i,total_files,progress)}
                        output_queue.put(('output',log_data))
            returncode=process.wait()
            if returncode==0 and not file_had_error:
                successful_files_count+=1
            else:
                full_error=" ".join(error_log) if error_log else f"处理 {file_name} 时发生未知错误 (代码: {returncode})。"
                output_queue.put(('error',{'log':full_error,'progress':calc_progress(i,total_files,99)}))
    except Exception as e:
        output_queue.put(('error',{'log':f"任务执行失败: {str(e)}"}))
    finally:
        found_files=[{"name":f.name,"url":f"/download/{task_id}/{f.name}"}for f in output_dir.glob('*.pdf')]
        final_log=f"处理完毕！成功 {successful_files_count}/{total_files} 个文件。"
        if successful_files_count<total_files: final_log+=" 部分任务失败，请检查日志。"
        output_queue.put(('done',{"files":found_files,"log":final_log}))

# --- Flask 路由 (与之前相同，无改动) ---
@app.route('/')
def index_route():
    lang=request.args.get('lang',session.get('lang','zh'))
    if lang not in translations:lang='zh'
    session['lang']=lang
    return render_template('index.html',texts=translations[lang],lang=lang)
@app.route('/translate', methods=['POST'])
def translate_start():
    task_id=str(uuid.uuid4())
    task_dir,input_dir,output_dir=TEMP_BASE_DIR/task_id,TEMP_BASE_DIR/task_id/"input",TEMP_BASE_DIR/task_id/"output"
    os.makedirs(input_dir,exist_ok=True);os.makedirs(output_dir,exist_ok=True)
    files=request.files.getlist('files')
    if not files or not files[0].filename: return jsonify({"error":"没有上传文件"}),400
    files_to_process=[{"path":input_dir/secure_filename(f.filename),"name":secure_filename(f.filename)}for f in files]
    for i,f in enumerate(files): f.save(files_to_process[i]["path"])
    task_queues[task_id]=queue.Queue()
    thread=threading.Thread(target=run_translation_task,args=(task_id,request.form,files_to_process))
    thread.daemon=True;thread.start()
    return jsonify({"task_id":task_id})
@app.route('/progress/<task_id>')
def progress_stream(task_id):
    def generate():
        q=task_queues.get(task_id)
        if not q:
            yield f"data: {json.dumps({'type':'error','data':{'log':'任务未找到或已完成。'}})}\n\n";return
        while True:
            try:
                msg_type,payload=q.get(timeout=120)
                yield f"data: {json.dumps({'type':msg_type,'data':payload})}\n\n"
                if msg_type=='done':break
            except queue.Empty:
                yield f"data: {json.dumps({'type':'error','data':{'log':'服务器超时，连接已断开。'}})}\n\n";break
        if task_id in task_queues:del task_queues[task_id]
    return Response(generate(),mimetype='text/event-stream')
@app.route('/service-worker.js')
def service_worker():return send_from_directory('static','service-worker.js')
@app.route('/manifest.json')
def manifest():return send_from_directory('static','manifest.json')
@app.route('/download/<task_id>/<filename>')
def download_file(task_id,filename):return send_from_directory(TEMP_BASE_DIR/task_id/"output",filename,as_attachment=True)
@app.route('/download_zip/<task_id>')
def download_zip(task_id):
    output_dir=TEMP_BASE_DIR/task_id/"output"
    if not output_dir.exists():return"任务不存在",404
    zip_buffer=io.BytesIO()
    with zipfile.ZipFile(zip_buffer,'w',zipfile.ZIP_DEFLATED)as zf:
        for f in output_dir.glob('*.pdf'):zf.write(f,f.name)
    zip_buffer.seek(0)
    return send_file(zip_buffer,mimetype='application/zip',as_attachment=True,download_name=f'translated_files_{task_id}.zip')
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)