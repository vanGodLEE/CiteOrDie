import tiktoken
import openai
import logging
import os
from datetime import datetime
import time
import json
import PyPDF2
import copy
import asyncio
import pymupdf
from io import BytesIO
from dotenv import load_dotenv
load_dotenv()
import logging
import yaml
from pathlib import Path
from types import SimpleNamespace as config

API_KEY = os.getenv("LLM_API_KEY")
BASE_URL = os.getenv("LLM_API_BASE")

# 429 rate-limit fallback: new key first, old key as backward-compat
FALLBACK_LLM_NAMES = (os.getenv("FALLBACK_LLM_NAMES") or os.getenv("FALLBACK_MODELS", "")).strip()
_FALLBACK_MODEL_LIST = [m.strip() for m in FALLBACK_LLM_NAMES.split(",") if m.strip()] if FALLBACK_LLM_NAMES else []

# 预加载一个通用 tokenizer（OpenAI 生态里最常用、兼容中英文）
_DEFAULT_ENCODING = tiktoken.get_encoding("cl100k_base")

def get_tokenizer(model: str | None = None):
    """
    安全获取 tokenizer：
    - 如果是 OpenAI 官方模型名，优先用 encoding_for_model
    - 否则（deepseek-chat、自定义模型名等）回退到 cl100k_base
    """
    if not model:
        return _DEFAULT_ENCODING

    try:
        # 对 gpt-4o / gpt-4o-mini 这类有效
        return tiktoken.encoding_for_model(model)
    except KeyError:
        # deepseek-chat 等非 OpenAI 名字，直接用通用编码
        return _DEFAULT_ENCODING

def count_tokens(text, model=None):
    if not text:
        return 0
    enc = get_tokenizer(model)
    tokens = enc.encode(text)
    return len(tokens)

def ChatGPT_API_with_finish_reason(model, prompt, api_key=API_KEY, chat_history=None):
    # 构建模型列表：主模型 + 备用模型
    all_models = [model] + _FALLBACK_MODEL_LIST
    max_retries = 10
    client = openai.OpenAI(api_key=api_key, base_url=BASE_URL)
    
    # 遍历所有可用模型
    for model_idx, current_model in enumerate(all_models):
        for i in range(max_retries):
            try:
                if chat_history:
                    messages = chat_history
                    messages.append({"role": "user", "content": prompt})
                else:
                    messages = [{"role": "user", "content": prompt}]
                
                response = client.chat.completions.create(
                    model=current_model,
                    messages=messages,
                    temperature=0,
                )
                
                if model_idx > 0:
                    logging.info(f"✓ 备用模型成功: {current_model}")
                    
                if response.choices[0].finish_reason == "length":
                    return response.choices[0].message.content, "max_output_reached"
                else:
                    return response.choices[0].message.content, "finished"

            except Exception as e:
                error_str = str(e).lower()
                # 检测429限流错误
                if "429" in error_str or "rate" in error_str or "quota" in error_str:
                    if model_idx < len(all_models) - 1:
                        # 还有备用模型，立即切换
                        logging.warning(f"⚠️ 模型 {current_model} 遇到429限流，切换到下一个备用模型...")
                        break  # 跳出重试循环，尝试下一个模型
                    else:
                        # 已是最后一个模型，抛出异常
                        logging.error(f"所有模型都遇到429限流，最后一个模型: {current_model}")
                        raise
                
                # 其他错误继续重试
                print('************* Retrying *************')
                logging.error(f"Error: {e}")
                if i < max_retries - 1:
                    time.sleep(1)
                else:
                    # 当前模型重试次数用尽
                    if model_idx < len(all_models) - 1:
                        # 还有备用模型，切换
                        logging.warning(f"模型 {current_model} 达到最大重试次数，切换到下一个备用模型...")
                        break
                    else:
                        logging.error('所有模型都失败，最大重试次数已达')
                        return "Error", "error"
    
    return "Error", "error"



def ChatGPT_API(model, prompt, api_key=API_KEY, chat_history=None):
    # 构建模型列表：主模型 + 备用模型
    all_models = [model] + _FALLBACK_MODEL_LIST
    max_retries = 10
    client = openai.OpenAI(api_key=api_key, base_url=BASE_URL)
    
    # 遍历所有可用模型
    for model_idx, current_model in enumerate(all_models):
        for i in range(max_retries):
            try:
                if chat_history:
                    messages = chat_history
                    messages.append({"role": "user", "content": prompt})
                else:
                    messages = [{"role": "user", "content": prompt}]
                
                response = client.chat.completions.create(
                    model=current_model,
                    messages=messages,
                    temperature=0,
                )
       
                if model_idx > 0:
                    logging.info(f"✓ 备用模型成功: {current_model}")
                return response.choices[0].message.content
            except Exception as e:
                error_str = str(e).lower()
                # 检测429限流错误
                if "429" in error_str or "rate" in error_str or "quota" in error_str:
                    if model_idx < len(all_models) - 1:
                        # 还有备用模型，立即切换
                        logging.warning(f"⚠️ 模型 {current_model} 遇到429限流，切换到下一个备用模型...")
                        break  # 跳出重试循环，尝试下一个模型
                    else:
                        # 已是最后一个模型，抛出异常
                        logging.error(f"所有模型都遇到429限流，最后一个模型: {current_model}")
                        raise
                
                # 其他错误继续重试
                print('************* Retrying *************')
                logging.error(f"Error: {e}")
                if i < max_retries - 1:
                    time.sleep(1)
                else:
                    # 当前模型重试次数用尽
                    if model_idx < len(all_models) - 1:
                        # 还有备用模型，切换
                        logging.warning(f"模型 {current_model} 达到最大重试次数，切换到下一个备用模型...")
                        break
                    else:
                        logging.error('所有模型都失败，最大重试次数已达')
                        return "Error"
    
    return "Error"
            

async def ChatGPT_API_async(model, prompt, api_key=API_KEY):
    # 构建模型列表：主模型 + 备用模型
    all_models = [model] + _FALLBACK_MODEL_LIST
    max_retries = 10
    messages = [{"role": "user", "content": prompt}]
    
    # 遍历所有可用模型
    for model_idx, current_model in enumerate(all_models):
        for i in range(max_retries):
            try:
                async with openai.AsyncOpenAI(api_key=api_key, base_url=BASE_URL) as client:
                    response = await client.chat.completions.create(
                        model=current_model,
                        messages=messages,
                        temperature=0,
                    )
                    if model_idx > 0:
                        logging.info(f"✓ 备用模型成功: {current_model}")
                    return response.choices[0].message.content
            except Exception as e:
                error_str = str(e).lower()
                # 检测429限流错误
                if "429" in error_str or "rate" in error_str or "quota" in error_str:
                    if model_idx < len(all_models) - 1:
                        # 还有备用模型，立即切换
                        logging.warning(f"⚠️ 模型 {current_model} 遇到429限流，切换到下一个备用模型...")
                        break  # 跳出重试循环，尝试下一个模型
                    else:
                        # 已是最后一个模型，抛出异常
                        logging.error(f"所有模型都遇到429限流，最后一个模型: {current_model}")
                        raise
                
                # 其他错误继续重试
                print('************* Retrying *************')
                logging.error(f"Error: {e}")
                if i < max_retries - 1:
                    await asyncio.sleep(1)
                else:
                    # 当前模型重试次数用尽
                    if model_idx < len(all_models) - 1:
                        # 还有备用模型，切换
                        logging.warning(f"模型 {current_model} 达到最大重试次数，切换到下一个备用模型...")
                        break
                    else:
                        logging.error('所有模型都失败，最大重试次数已达')
                        return "Error"
    
    return "Error"
            
            
def get_json_content(response):
    start_idx = response.find("```json")
    if start_idx != -1:
        start_idx += 7
        response = response[start_idx:]
        
    end_idx = response.rfind("```")
    if end_idx != -1:
        response = response[:end_idx]
    
    json_content = response.strip()
    return json_content
         

def extract_json(content):
    try:
        # First, try to extract JSON enclosed within ```json and ```
        start_idx = content.find("```json")
        if start_idx != -1:
            start_idx += 7  # Adjust index to start after the delimiter
            end_idx = content.rfind("```")
            json_content = content[start_idx:end_idx].strip()
        else:
            # If no delimiters, assume entire content could be JSON
            json_content = content.strip()

        # Clean up common issues that might cause parsing errors
        json_content = json_content.replace('None', 'null')  # Replace Python None with JSON null
        json_content = json_content.replace('\n', ' ').replace('\r', ' ')  # Remove newlines
        json_content = ' '.join(json_content.split())  # Normalize whitespace

        # Attempt to parse and return the JSON object
        return json.loads(json_content)
    except json.JSONDecodeError as e:
        logging.error(f"Failed to extract JSON: {e}")
        # Try to clean up the content further if initial parsing fails
        try:
            # Remove any trailing commas before closing brackets/braces
            json_content = json_content.replace(',]', ']').replace(',}', '}')
            return json.loads(json_content)
        except:
            logging.error("Failed to parse JSON even after cleanup")
            return {}
    except Exception as e:
        logging.error(f"Unexpected error while extracting JSON: {e}")
        return {}

def write_node_id(data, node_id=0):
    if isinstance(data, dict):
        data['node_id'] = str(node_id).zfill(4)
        node_id += 1
        for key in list(data.keys()):
            if 'nodes' in key:
                node_id = write_node_id(data[key], node_id)
    elif isinstance(data, list):
        for index in range(len(data)):
            node_id = write_node_id(data[index], node_id)
    return node_id

def get_nodes(structure):
    if isinstance(structure, dict):
        structure_node = copy.deepcopy(structure)
        structure_node.pop('nodes', None)
        nodes = [structure_node]
        for key in list(structure.keys()):
            if 'nodes' in key:
                nodes.extend(get_nodes(structure[key]))
        return nodes
    elif isinstance(structure, list):
        nodes = []
        for item in structure:
            nodes.extend(get_nodes(item))
        return nodes
    
def structure_to_list(structure):
    if isinstance(structure, dict):
        nodes = []
        nodes.append(structure)
        if 'nodes' in structure:
            nodes.extend(structure_to_list(structure['nodes']))
        return nodes
    elif isinstance(structure, list):
        nodes = []
        for item in structure:
            nodes.extend(structure_to_list(item))
        return nodes

    
def get_leaf_nodes(structure):
    if isinstance(structure, dict):
        if not structure['nodes']:
            structure_node = copy.deepcopy(structure)
            structure_node.pop('nodes', None)
            return [structure_node]
        else:
            leaf_nodes = []
            for key in list(structure.keys()):
                if 'nodes' in key:
                    leaf_nodes.extend(get_leaf_nodes(structure[key]))
            return leaf_nodes
    elif isinstance(structure, list):
        leaf_nodes = []
        for item in structure:
            leaf_nodes.extend(get_leaf_nodes(item))
        return leaf_nodes

def is_leaf_node(data, node_id):
    # Helper function to find the node by its node_id
    def find_node(data, node_id):
        if isinstance(data, dict):
            if data.get('node_id') == node_id:
                return data
            for key in data.keys():
                if 'nodes' in key:
                    result = find_node(data[key], node_id)
                    if result:
                        return result
        elif isinstance(data, list):
            for item in data:
                result = find_node(item, node_id)
                if result:
                    return result
        return None

    # Find the node with the given node_id
    node = find_node(data, node_id)

    # Check if the node is a leaf node
    if node and not node.get('nodes'):
        return True
    return False

def get_last_node(structure):
    return structure[-1]


def extract_text_from_pdf(pdf_path):
    pdf_reader = PyPDF2.PdfReader(pdf_path)
    ###return text not list 
    text=""
    for page_num in range(len(pdf_reader.pages)):
        page = pdf_reader.pages[page_num]
        text+=page.extract_text()
    return text

def get_pdf_title(pdf_path):
    pdf_reader = PyPDF2.PdfReader(pdf_path)
    meta = pdf_reader.metadata
    title = meta.title if meta and meta.title else 'Untitled'
    return title

def get_text_of_pages(pdf_path, start_page, end_page, tag=True):
    pdf_reader = PyPDF2.PdfReader(pdf_path)
    text = ""
    for page_num in range(start_page-1, end_page):
        page = pdf_reader.pages[page_num]
        page_text = page.extract_text()
        if tag:
            text += f"<start_index_{page_num+1}>\n{page_text}\n<end_index_{page_num+1}>\n"
        else:
            text += page_text
    return text

def get_first_start_page_from_text(text):
    start_page = -1
    start_page_match = re.search(r'<start_index_(\d+)>', text)
    if start_page_match:
        start_page = int(start_page_match.group(1))
    return start_page

def get_last_start_page_from_text(text):
    start_page = -1
    # Find all matches of start_index tags
    start_page_matches = re.finditer(r'<start_index_(\d+)>', text)
    # Convert iterator to list and get the last match if any exist
    matches_list = list(start_page_matches)
    if matches_list:
        start_page = int(matches_list[-1].group(1))
    return start_page


def sanitize_filename(filename, replacement='-'):
    # In Linux, only '/' and '\0' (null) are invalid in filenames.
    # Null can't be represented in strings, so we only handle '/'.
    return filename.replace('/', replacement)

def get_pdf_name(pdf_path):
    # Extract PDF name
    if isinstance(pdf_path, str):
        pdf_name = os.path.basename(pdf_path)
    elif isinstance(pdf_path, BytesIO):
        pdf_reader = PyPDF2.PdfReader(pdf_path)
        meta = pdf_reader.metadata
        pdf_name = meta.title if meta and meta.title else 'Untitled'
        pdf_name = sanitize_filename(pdf_name)
    return pdf_name


class JsonLogger:
    def __init__(self, file_path):
        # Extract PDF name for logger name
        pdf_name = get_pdf_name(file_path)
            
        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filename = f"{pdf_name}_{current_time}.json"
        os.makedirs("./logs", exist_ok=True)
        # Initialize empty list to store all messages
        self.log_data = []

    def log(self, level, message, **kwargs):
        if isinstance(message, dict):
            self.log_data.append(message)
        else:
            self.log_data.append({'message': message})
        # Add new message to the log data
        
        # Write entire log data to file
        with open(self._filepath(), "w") as f:
            json.dump(self.log_data, f, indent=2)

    def info(self, message, **kwargs):
        self.log("INFO", message, **kwargs)

    def error(self, message, **kwargs):
        self.log("ERROR", message, **kwargs)

    def debug(self, message, **kwargs):
        self.log("DEBUG", message, **kwargs)

    def exception(self, message, **kwargs):
        kwargs["exception"] = True
        self.log("ERROR", message, **kwargs)

    def _filepath(self):
        return os.path.join("logs", self.filename)
    



def list_to_tree(data):
    def get_parent_structure(structure):
        """Helper function to get the parent structure code"""
        if not structure:
            return None
        parts = str(structure).split('.')
        return '.'.join(parts[:-1]) if len(parts) > 1 else None
    
    # First pass: Create nodes and track parent-child relationships
    nodes = {}
    root_nodes = []
    
    for item in data:
        structure = item.get('structure')
        node = {
            'title': item.get('title'),
            'start_index': item.get('start_index'),
            'end_index': item.get('end_index'),
            'nodes': []
        }
        
        nodes[structure] = node
        
        # Find parent
        parent_structure = get_parent_structure(structure)
        
        if parent_structure:
            # Add as child to parent if parent exists
            if parent_structure in nodes:
                nodes[parent_structure]['nodes'].append(node)
            else:
                root_nodes.append(node)
        else:
            # No parent, this is a root node
            root_nodes.append(node)
    
    # Helper function to clean empty children arrays
    def clean_node(node):
        if not node['nodes']:
            del node['nodes']
        else:
            for child in node['nodes']:
                clean_node(child)
        return node
    
    # Clean and return the tree
    return [clean_node(node) for node in root_nodes]

def add_preface_if_needed(data):
    if not isinstance(data, list) or not data:
        return data

    if data[0]['physical_index'] is not None and data[0]['physical_index'] > 1:
        preface_node = {
            "structure": "0",
            "title": "Preface",
            "physical_index": 1,
        }
        data.insert(0, preface_node)
    return data



def get_page_tokens(pdf_path, pdf_parser="PyPDF2"):
    # 这里用 get_encoding，而不是 encoding_for_model
    enc = tiktoken.get_encoding("cl100k_base")

    if pdf_parser == "PyPDF2":
        pdf_reader = PyPDF2.PdfReader(pdf_path)
        page_list = []
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            page_text = page.extract_text() or ""
            token_length = len(enc.encode(page_text))
            page_list.append((page_text, token_length))
        return page_list

    elif pdf_parser == "PyMuPDF":
        if isinstance(pdf_path, BytesIO):
            pdf_stream = pdf_path
            doc = pymupdf.open(stream=pdf_stream, filetype="pdf")
        elif isinstance(pdf_path, str) and os.path.isfile(pdf_path) and pdf_path.lower().endswith(".pdf"):
            doc = pymupdf.open(pdf_path)
        else:
            raise ValueError("Invalid pdf_path")

        page_list = []
        for page in doc:
            page_text = page.get_text() or ""
            token_length = len(enc.encode(page_text))
            page_list.append((page_text, token_length))
        return page_list

    else:
        raise ValueError(f"Unsupported PDF parser: {pdf_parser}")

        

def get_text_of_pdf_pages(pdf_pages, start_page, end_page):
    text = ""
    for page_num in range(start_page-1, end_page):
        text += pdf_pages[page_num][0]
    return text

def get_text_of_pdf_pages_with_labels(pdf_pages, start_page, end_page):
    text = ""
    for page_num in range(start_page-1, end_page):
        text += f"<physical_index_{page_num+1}>\n{pdf_pages[page_num][0]}\n<physical_index_{page_num+1}>\n"
    return text

def get_number_of_pages(pdf_path):
    pdf_reader = PyPDF2.PdfReader(pdf_path)
    num = len(pdf_reader.pages)
    return num



def post_processing(structure, end_physical_index):
    # First convert page_number to start_index in flat list
    for i, item in enumerate(structure):
        item['start_index'] = item.get('physical_index')
        if i < len(structure) - 1:
            if structure[i + 1].get('appear_start') == 'yes':
                item['end_index'] = structure[i + 1]['physical_index']-1
            else:
                item['end_index'] = structure[i + 1]['physical_index']
        else:
            item['end_index'] = end_physical_index
    tree = list_to_tree(structure)
    if len(tree)!=0:
        return tree
    else:
        ### remove appear_start 
        for node in structure:
            node.pop('appear_start', None)
            node.pop('physical_index', None)
        return structure

def clean_structure_post(data):
    if isinstance(data, dict):
        data.pop('page_number', None)
        data.pop('start_index', None)
        data.pop('end_index', None)
        if 'nodes' in data:
            clean_structure_post(data['nodes'])
    elif isinstance(data, list):
        for section in data:
            clean_structure_post(section)
    return data

def remove_fields(data, fields=['text']):
    if isinstance(data, dict):
        return {k: remove_fields(v, fields)
            for k, v in data.items() if k not in fields}
    elif isinstance(data, list):
        return [remove_fields(item, fields) for item in data]
    return data

def print_toc(tree, indent=0):
    for node in tree:
        print('  ' * indent + node['title'])
        if node.get('nodes'):
            print_toc(node['nodes'], indent + 1)

def print_json(data, max_len=40, indent=2):
    def simplify_data(obj):
        if isinstance(obj, dict):
            return {k: simplify_data(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [simplify_data(item) for item in obj]
        elif isinstance(obj, str) and len(obj) > max_len:
            return obj[:max_len] + '...'
        else:
            return obj
    
    simplified = simplify_data(data)
    print(json.dumps(simplified, indent=indent, ensure_ascii=False))


def remove_structure_text(data):
    if isinstance(data, dict):
        data.pop('text', None)
        if 'nodes' in data:
            remove_structure_text(data['nodes'])
    elif isinstance(data, list):
        for item in data:
            remove_structure_text(item)
    return data


def check_token_limit(structure, limit=110000):
    list = structure_to_list(structure)
    for node in list:
        num_tokens = count_tokens(node['text'], model='gpt-4o')
        if num_tokens > limit:
            print(f"Node ID: {node['node_id']} has {num_tokens} tokens")
            print("Start Index:", node['start_index'])
            print("End Index:", node['end_index'])
            print("Title:", node['title'])
            print("\n")


def convert_physical_index_to_int(data):
    """
    将physical_index字符串转换为整数。
    
    支持的格式:
    - <physical_index_9>
    - physical_index_9
    - 已经是整数的情况
    
    增强的鲁棒性：
    - 处理None值
    - 处理转换失败的情况
    - 添加详细的异常处理
    
    Args:
        data: 列表、字符串或其他类型的数据
        
    Returns:
        转换后的数据，失败的项会被设为None
    """
    if isinstance(data, list):
        for i in range(len(data)):
            # 检查是否为字典且包含physical_index键
            if isinstance(data[i], dict) and 'physical_index' in data[i]:
                physical_index = data[i]['physical_index']
                
                # 如果已经是None，保持不变
                if physical_index is None:
                    continue
                
                # 如果已经是整数，保持不变
                if isinstance(physical_index, int):
                    continue
                
                # 如果是字符串，尝试转换
                if isinstance(physical_index, str):
                    try:
                        if physical_index.startswith('<physical_index_'):
                            # 格式: <physical_index_9>
                            num_str = physical_index.split('_')[-1].rstrip('>').strip()
                            data[i]['physical_index'] = int(num_str)
                        elif physical_index.startswith('physical_index_'):
                            # 格式: physical_index_9
                            num_str = physical_index.split('_')[-1].strip()
                            data[i]['physical_index'] = int(num_str)
                        else:
                            # 尝试直接转换为整数
                            data[i]['physical_index'] = int(physical_index)
                    except (ValueError, IndexError, AttributeError) as e:
                        # 转换失败，设为None
                        logging.warning(f"⚠️ 无法转换physical_index: {physical_index}, 错误: {e}")
                        data[i]['physical_index'] = None
                else:
                    # 既不是字符串也不是整数，设为None
                    logging.warning(f"⚠️ physical_index类型不支持: {type(physical_index)}")
                    data[i]['physical_index'] = None
                    
    elif isinstance(data, str):
        # 单个字符串的转换
        try:
            if data.startswith('<physical_index_'):
                num_str = data.split('_')[-1].rstrip('>').strip()
                return int(num_str)
            elif data.startswith('physical_index_'):
                num_str = data.split('_')[-1].strip()
                return int(num_str)
            else:
                # 尝试直接转换
                return int(data)
        except (ValueError, IndexError, AttributeError):
            # 转换失败返回None
            return None
            
    elif isinstance(data, int):
        # 已经是整数，直接返回
        return data
    
    elif data is None:
        # None值保持不变
        return None
        
    return data


def convert_page_to_int(data):
    for item in data:
        if 'page' in item and isinstance(item['page'], str):
            try:
                item['page'] = int(item['page'])
            except ValueError:
                # Keep original value if conversion fails
                pass
    return data


def add_node_text(node, pdf_pages):
    if isinstance(node, dict):
        start_page = node.get('start_index')
        end_page = node.get('end_index')
        node['text'] = get_text_of_pdf_pages(pdf_pages, start_page, end_page)
        if 'nodes' in node:
            add_node_text(node['nodes'], pdf_pages)
    elif isinstance(node, list):
        for index in range(len(node)):
            add_node_text(node[index], pdf_pages)
    return


def add_node_text_with_labels(node, pdf_pages):
    if isinstance(node, dict):
        start_page = node.get('start_index')
        end_page = node.get('end_index')
        node['text'] = get_text_of_pdf_pages_with_labels(pdf_pages, start_page, end_page)
        if 'nodes' in node:
            add_node_text_with_labels(node['nodes'], pdf_pages)
    elif isinstance(node, list):
        for index in range(len(node)):
            add_node_text_with_labels(node[index], pdf_pages)
    return


async def generate_node_summary(node, model=None):
    prompt = f"""You are given a part of a document, your task is to generate a description of the partial document about what are main points covered in the partial document.

    Partial Document Text: {node['text']}
    
    Directly return the description, do not include any other text.
    """
    response = await ChatGPT_API_async(model, prompt)
    return response


async def generate_summaries_for_structure(structure, model=None):
    nodes = structure_to_list(structure)
    tasks = [generate_node_summary(node, model=model) for node in nodes]
    summaries = await asyncio.gather(*tasks)
    
    for node, summary in zip(nodes, summaries):
        node['summary'] = summary
    return structure


def create_clean_structure_for_description(structure):
    """
    Create a clean structure for document description generation,
    excluding unnecessary fields like 'text'.
    """
    if isinstance(structure, dict):
        clean_node = {}
        # Only include essential fields for description
        for key in ['title', 'node_id', 'summary', 'prefix_summary']:
            if key in structure:
                clean_node[key] = structure[key]
        
        # Recursively process child nodes
        if 'nodes' in structure and structure['nodes']:
            clean_node['nodes'] = create_clean_structure_for_description(structure['nodes'])
        
        return clean_node
    elif isinstance(structure, list):
        return [create_clean_structure_for_description(item) for item in structure]
    else:
        return structure


def generate_doc_description(structure, model=None):
    prompt = f"""Your are an expert in generating descriptions for a document.
    You are given a structure of a document. Your task is to generate a one-sentence description for the document, which makes it easy to distinguish the document from other documents.
        
    Document Structure: {structure}
    
    Directly return the description, do not include any other text.
    """
    response = ChatGPT_API(model, prompt)
    return response


def reorder_dict(data, key_order):
    if not key_order:
        return data
    return {key: data[key] for key in key_order if key in data}


def format_structure(structure, order=None):
    if not order:
        return structure
    if isinstance(structure, dict):
        if 'nodes' in structure:
            structure['nodes'] = format_structure(structure['nodes'], order)
        if not structure.get('nodes'):
            structure.pop('nodes', None)
        structure = reorder_dict(structure, order)
    elif isinstance(structure, list):
        structure = [format_structure(item, order) for item in structure]
    return structure


class ConfigLoader:
    def __init__(self, default_path: str = None):
        if default_path is None:
            default_path = Path(__file__).parent / "config.yaml"
        self._default_dict = self._load_yaml(default_path)

    @staticmethod
    def _load_yaml(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _validate_keys(self, user_dict):
        unknown_keys = set(user_dict) - set(self._default_dict)
        if unknown_keys:
            raise ValueError(f"Unknown config keys: {unknown_keys}")

    def load(self, user_opt=None) -> config:
        """
        Load the configuration, merging user options with default values.
        """
        if user_opt is None:
            user_dict = {}
        elif isinstance(user_opt, config):
            user_dict = vars(user_opt)
        elif isinstance(user_opt, dict):
            user_dict = user_opt
        else:
            raise TypeError("user_opt must be dict, config(SimpleNamespace) or None")

        self._validate_keys(user_dict)
        merged = {**self._default_dict, **user_dict}
        return config(**merged)