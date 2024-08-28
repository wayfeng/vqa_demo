# VQA demo

Demo VQA app running on Intel dGPU.

## Install IPEX-LLM

Make sure to install GPU driver and OneAPI according to this [document](https://github.com/intel-analytics/ipex-llm/blob/main/docs/mddocs/Quickstart/install_linux_gpu.md).

IPEX-LLM needs `python3.11`.

```bash
sudo apt install python3.11 python3.11-venv
```

Create virtual environment.

```bash
python -m venv .env
```

Install IPEX-LLM and dependencies.

```bash
source .env/bin/activate
pip install -U pip
pip install --pre --upgrade ipex-llm[xpu] --extra-index-url https://pytorch-extension.intel.com/release-whl/stable/xpu/cn/
pip install -r requirements.txt
```

## Qwen-VL demo

Download Qwen-VL pretrained model.

```bash
huggingface-cli download Qwen/Qwen-VL-Chat
```

Run gradio app.

```bash
source /opt/intel/oneapi/setvars.sh
GRADIO_SERVER_NAME=0.0.0.0 python qwen_vl_ipex.py --server-name 0.0.0.0
```
