"""A simple web interactive chat demo based on gradio."""

from argparse import ArgumentParser
from pathlib import Path

import copy
import gradio as gr
import os
import re
import secrets
import tempfile
import torch
from transformers import AutoTokenizer
from ipex_llm.transformers import AutoModelForCausalLM

torch.manual_seed(1234)

MODEL_ID = 'Qwen/Qwen-VL-Chat'
MODEL_PATH = Path('./models/Qwen-VL-Chat')
BOX_TAG_PATTERN = r"<box>([\s\S]*?)</box>"
PUNCTUATION = "！？。＂＃＄％＆＇（）＊＋，－／：；＜＝＞＠［＼］＾＿｀｛｜｝～｟｠｢｣､、〃》「」『』【】〔〕〖〗〘〙〚〛〜〝〞〟〰〾〿–—‘’‛“”„‟…‧﹏."


def _get_args():
    parser = ArgumentParser()
    parser.add_argument("--server-port", type=int, default=8000,
                        help="Demo server port.")
    parser.add_argument("--server-name", type=str, default="127.0.0.1",
                        help="Demo server name.")

    return parser.parse_args()


def _load_model_tokenizer(args):
    if MODEL_PATH.exists():
        tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
        model = AutoModelForCausalLM.load_low_bit(MODEL_PATH, trust_remote_code=True,
                            modules_to_not_convert=['c_fc', 'out_proj']).eval().to('xpu')
    else:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(MODEL_ID, load_in_4bit=True, trust_remote_code=True, 
                    modules_to_not_convert=['c_fc', 'out_proj'], torch_dtype=torch.float32).eval().to('xpu')

    return model, tokenizer


def _parse_text(text):
    lines = text.split("\n")
    lines = [line for line in lines if line != ""]
    count = 0
    for i, line in enumerate(lines):
        if "```" in line:
            count += 1
            items = line.split("`")
            if count % 2 == 1:
                lines[i] = f'<pre><code class="language-{items[-1]}">'
            else:
                lines[i] = f"<br></code></pre>"
        else:
            if i > 0:
                if count % 2 == 1:
                    line = line.replace("`", r"\`")
                    line = line.replace("<", "&lt;")
                    line = line.replace(">", "&gt;")
                    line = line.replace(" ", "&nbsp;")
                    line = line.replace("*", "&ast;")
                    line = line.replace("_", "&lowbar;")
                    line = line.replace("-", "&#45;")
                    line = line.replace(".", "&#46;")
                    line = line.replace("!", "&#33;")
                    line = line.replace("(", "&#40;")
                    line = line.replace(")", "&#41;")
                    line = line.replace("$", "&#36;")
                lines[i] = "<br>" + line
    text = "".join(lines)
    return text

def _remove_image_special(text):
    text = text.replace('<ref>', '').replace('</ref>', '')
    return re.sub(r'<box>.*?(</box>|$)', '', text)

def _launch_demo(args, model, tokenizer):
    uploaded_file_dir = os.environ.get("GRADIO_TEMP_DIR") or str(
        Path(tempfile.gettempdir()) / "gradio"
    )

    def predict(_chatbot, task_history):
        chat_query = _chatbot[-1][0]
        query = task_history[-1][0]
        print("User: " + _parse_text(query))
        history_cp = copy.deepcopy(task_history)
        full_response = ""

        history_filter = []
        pic_idx = 1
        pre = ""
        for i, (q, a) in enumerate(history_cp):
            if isinstance(q, (tuple, list)):
                q = f'Picture {pic_idx}: <img>{q[0]}</img>'
                pre += q + '\n'
                pic_idx += 1
            else:
                pre += q
                history_filter.append((pre, a))
                pre = ""
        history, message = history_filter[:-1], history_filter[-1][0]
        # response, history = model.chat(tokenizer, message, history=history)
        for response in model.chat_stream(tokenizer, message, history=history):
            _chatbot[-1] = (_parse_text(chat_query), _remove_image_special(_parse_text(response)))

            yield _chatbot
            full_response = _parse_text(response)

        response = full_response
        history.append((message, response))
        image = tokenizer.draw_bbox_on_latest_picture(response, history)
        if image is not None:
            temp_dir = secrets.token_hex(20)
            temp_dir = Path(uploaded_file_dir) / temp_dir
            temp_dir.mkdir(exist_ok=True, parents=True)
            name = f"tmp{secrets.token_hex(5)}.jpg"
            filename = temp_dir / name
            image.save(str(filename))
            _chatbot.append((None, (str(filename),)))
        else:
            _chatbot[-1] = (_parse_text(chat_query), response)
        # full_response = _parse_text(response)

        task_history[-1] = (query, full_response)
        print("Qwen-VL-Chat: " + _parse_text(full_response))
        yield _chatbot

    def regenerate(_chatbot, task_history):
        if not task_history:
            return _chatbot
        item = task_history[-1]
        if item[1] is None:
            return _chatbot
        task_history[-1] = (item[0], None)
        chatbot_item = _chatbot.pop(-1)
        if chatbot_item[0] is None:
            _chatbot[-1] = (_chatbot[-1][0], None)
        else:
            _chatbot.append((chatbot_item[0], None))
        return predict(_chatbot, task_history)

    def add_text(history, task_history, text):
        task_text = text
        if len(text) >= 2 and text[-1] in PUNCTUATION and text[-2] not in PUNCTUATION:
            task_text = text[:-1]
        history = history + [(_parse_text(text), None)]
        task_history = task_history + [(task_text, None)]
        return history, task_history, ""

    def add_file(history, task_history, file):
        history = history + [((file.name,), None)]
        task_history = task_history + [((file.name,), None)]
        return history, task_history

    def reset_user_input():
        return gr.update(value="")

    def reset_state(task_history):
        task_history.clear()
        return []

    with gr.Blocks() as demo:
        gr.Markdown("""<center><font size=8>Qwen-VL-Chat Bot</center>""")

        chatbot = gr.Chatbot(label='Chat', elem_classes="control-height", height=750)
        query = gr.Textbox(lines=2, label='Input')
        task_history = gr.State([])

        with gr.Row():
            empty_bin = gr.Button("🧹 Clear History (清除历史)")
            submit_btn = gr.Button("🚀 Submit (发送)")
            regen_btn = gr.Button("🤔️ Regenerate (重试)")
            addfile_btn = gr.UploadButton("📁 Upload (上传文件)", file_types=["image"])

        submit_btn.click(add_text, [chatbot, task_history, query], [chatbot, task_history]).then(
            predict, [chatbot, task_history], [chatbot], show_progress=True
        )
        submit_btn.click(reset_user_input, [], [query])
        empty_bin.click(reset_state, [task_history], [chatbot], show_progress=True)
        regen_btn.click(regenerate, [chatbot, task_history], [chatbot], show_progress=True)
        addfile_btn.upload(add_file, [chatbot, task_history, addfile_btn], [chatbot, task_history], show_progress=True)

    demo.queue().launch(
        server_port=args.server_port,
        server_name=args.server_name,
    )


if __name__ == '__main__':
    args = _get_args()
    model, tokenizer = _load_model_tokenizer(args)
    _launch_demo(args, model, tokenizer)