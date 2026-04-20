import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import re
import time
import json
import random
import hashlib
import warnings
from urllib.parse import urljoin, urlparse, quote, unquote, parse_qs, urlencode
import requests
import urllib3
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO

warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', message='Unverified HTTPS request')


class DebugLogger:
    def __init__(self, log_callback=None, debug_mode=True):
        self.log_callback = log_callback
        self.debug_mode = debug_mode
    
    def info(self, message):
        if self.log_callback:
            self.log_callback(f"[INFO] {message}")
    
    def debug(self, message):
        if self.debug_mode and self.log_callback:
            self.log_callback(f"[DEBUG] {message}")
    
    def error(self, message):
        if self.log_callback:
            self.log_callback(f"[ERROR] {message}")
    
    def success(self, message):
        if self.log_callback:
            self.log_callback(f"[✓] {message}")


class ImageDeduplicator:
    def __init__(self, logger=None):
        self.logger = logger
        self.md5_hashes = set()
        self.phash_hashes = set()
        self.duplicate_count = 0
    
    def compute_md5(self, content):
        return hashlib.md5(content).hexdigest()
    
    def compute_phash(self, img, hash_size=8, highfreq_factor=4):
        try:
            img_size = hash_size * highfreq_factor
            img = img.convert('L')
            img = img.resize((img_size, img_size), Image.Resampling.LANCZOS)
            
            pixels = []
            for row in range(img_size):
                for col in range(img_size):
                    pixels.append(img.getpixel((col, row)))
            
            dct = self._dct_2d(pixels, img_size)
            
            dct_low = []
            for row in range(hash_size):
                for col in range(hash_size):
                    dct_low.append(dct[row * img_size + col])
            
            avg = sum(dct_low) / len(dct_low)
            
            hash_bits = []
            for value in dct_low:
                hash_bits.append('1' if value > avg else '0')
            
            hash_hex = ''.join(hash_bits)
            hash_int = int(hash_hex, 2)
            return hash_int
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"pHash计算失败: {e}")
            return None
    
    def _dct_2d(self, pixels, size):
        try:
            import math
            dct = [0.0] * (size * size)
            
            for u in range(size):
                for v in range(size):
                    sum_val = 0.0
                    for i in range(size):
                        for j in range(size):
                            cos_u = math.cos((2 * i + 1) * u * math.pi / (2 * size))
                            cos_v = math.cos((2 * j + 1) * v * math.pi / (2 * size))
                            sum_val += pixels[i * size + j] * cos_u * cos_v
                    
                    cu = 1.0 / math.sqrt(2) if u == 0 else 1.0
                    cv = 1.0 / math.sqrt(2) if v == 0 else 1.0
                    dct[u * size + v] = cu * cv * sum_val / 4.0
            
            return dct
        except Exception as e:
            if self.logger:
                self.logger.error(f"DCT计算失败: {e}")
            return [0.0] * (size * size)
    
    def hamming_distance(self, hash1, hash2):
        xor_result = hash1 ^ hash2
        return bin(xor_result).count('1')
    
    def is_duplicate(self, content=None, img=None, method='md5', phash_threshold=5):
        if method == 'md5' and content:
            md5_hash = self.compute_md5(content)
            if md5_hash in self.md5_hashes:
                return True
            self.md5_hashes.add(md5_hash)
            return False
        
        elif method == 'phash' and img:
            phash = self.compute_phash(img)
            if phash is None:
                return False
            
            for existing_hash in self.phash_hashes:
                distance = self.hamming_distance(phash, existing_hash)
                if distance <= phash_threshold:
                    return True
            
            self.phash_hashes.add(phash)
            return False
        
        elif method == 'both':
            if content:
                md5_hash = self.compute_md5(content)
                if md5_hash in self.md5_hashes:
                    return True
                self.md5_hashes.add(md5_hash)
            
            if img:
                phash = self.compute_phash(img)
                if phash is not None:
                    for existing_hash in self.phash_hashes:
                        distance = self.hamming_distance(phash, existing_hash)
                        if distance <= phash_threshold:
                            return True
                    self.phash_hashes.add(phash)
            
            return False
        
        return False
    
    def reset(self):
        self.md5_hashes.clear()
        self.phash_hashes.clear()
        self.duplicate_count = 0
    
    def get_stats(self):
        return {
            'md5_count': len(self.md5_hashes),
            'phash_count': len(self.phash_hashes),
            'duplicate_count': self.duplicate_count
        }


class SearchEngineAdapter:
    @staticmethod
    def build_baidu_image_url_v2(keyword, page=1):
        pn = (page - 1) * 30
        params = {
            'tn': 'baiduimage',
            'word': keyword,
            'pn': pn,
            'rn': 30,
            'ie': 'utf-8',
            'oe': 'utf-8',
            'cl': 2,
            'lm': -1,
            'st': -1,
            'fm': 'result',
            'fr': '',
            'sf': 1,
            'fmq': '1355129544369_R',
            'pv': '',
            'ic': 0,
            'nc': 1,
            'z': '',
            'se': 1,
            'tab': 0,
            'width': '',
            'height': '',
            'face': 0,
            'istype': 2,
            'qc': '',
            'nc': 1,
            'pn': pn,
            'rn': 30,
            'tn': 'baiduimage',
            'word': keyword,
            'gsm': '5a'
        }
        query_string = urlencode(params, encoding='utf-8')
        return f"https://image.baidu.com/search/index?{query_string}"
    
    @staticmethod
    def build_baidu_image_ajax_url(keyword, page=1):
        pn = (page - 1) * 30
        params = {
            'tn': 'resultjson_com',
            'logid': '8840081919301210825',
            'ipn': 'rj',
            'ct': 201326592,
            'is': '',
            'fp': 'result',
            'fr': '',
            'word': keyword,
            'queryWord': keyword,
            'cl': 2,
            'lm': -1,
            'ie': 'utf-8',
            'oe': 'utf-8',
            'adpicid': '',
            'st': -1,
            'z': '',
            'ic': 0,
            'hd': '',
            'latest': '',
            'copyright': '',
            's': '',
            'se': '',
            'tab': '',
            'width': '',
            'height': '',
            'face': 0,
            'istype': 2,
            'qc': '',
            'nc': 1,
            'expermode': '',
            'nojc': '',
            'isAsync': '',
            'pn': pn,
            'rn': 30,
            'gsm': '3c',
            '1692189049873': ''
        }
        query_string = urlencode(params, encoding='utf-8')
        return f"https://image.baidu.com/search/acjson?{query_string}"
    
    @staticmethod
    def build_bing_image_url(keyword, page=1):
        first = (page - 1) * 35 + 1
        params = {
            'q': keyword,
            'first': first,
            'count': 35,
            'cw': 1920,
            'ch': 1080,
            'FORM': 'IBASEL',
            'tsc': 'ImageHoverTitle'
        }
        query_string = urlencode(params, encoding='utf-8')
        return f"https://www.bing.com/images/search?{query_string}"
    
    @staticmethod
    def build_google_image_url(keyword, page=1):
        start = (page - 1) * 20
        params = {
            'q': keyword,
            'tbm': 'isch',
            'start': start,
            'safe': 'off'
        }
        query_string = urlencode(params, encoding='utf-8')
        return f"https://www.google.com/search?{query_string}"
    
    @staticmethod
    def get_engine_from_url(url):
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        
        if 'baidu' in netloc:
            return 'baidu'
        elif 'bing' in netloc:
            return 'bing'
        elif 'google' in netloc:
            return 'google'
        else:
            return 'generic'


class ImageExtractor:
    @staticmethod
    def extract_from_baidu_html(html, logger=None):
        images = []
        
        if logger:
            logger.debug(f"HTML长度: {len(html)} 字符")
            if 'thumbURL' in html:
                logger.debug("✓ 找到 thumbURL 模式")
            if 'objURL' in html:
                logger.debug("✓ 找到 objURL 模式")
            if 'hoverURL' in html:
                logger.debug("✓ 找到 hoverURL 模式")
            if 'middleURL' in html:
                logger.debug("✓ 找到 middleURL 模式")
        
        patterns = [
            r'"thumbURL"\s*:\s*"(http[^"]+)"',
            r'"objURL"\s*:\s*"(http[^"]+)"',
            r'"hoverURL"\s*:\s*"(http[^"]+)"',
            r'"middleURL"\s*:\s*"(http[^"]+)"',
            r'"pageURL"\s*:\s*"(http[^"]+)"',
            r'"fromURL"\s*:\s*"(http[^"]+)"',
            r'"url"\s*:\s*"(http[^"]+\.(?:jpg|jpeg|png|gif|bmp|webp))"',
        ]
        
        for i, pattern in enumerate(patterns):
            matches = re.findall(pattern, html, re.IGNORECASE)
            if matches and logger:
                logger.debug(f"模式 {i+1} 找到 {len(matches)} 个URL")
            for match in matches:
                url = match.replace('\\/', '/')
                url = url.replace('\\u002F', '/')
                if url not in images:
                    images.append(url)
        
        url_pattern = r'(https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|gif|bmp|webp|svg))'
        matches = re.findall(url_pattern, html, re.IGNORECASE)
        if matches and logger:
            logger.debug(f"通用URL模式找到 {len(matches)} 个URL")
        for match in matches:
            if match not in images:
                images.append(match)
        
        soup = BeautifulSoup(html, 'lxml')
        
        img_tags = soup.find_all('img')
        if logger:
            logger.debug(f"BeautifulSoup找到 {len(img_tags)} 个img标签")
        
        for img in img_tags:
            attrs_to_check = [
                'src', 'data-src', 'data-lazy', 'data-original',
                'data-srcset', 'srcset', 'data-url', 'data-imgurl',
                'data-thumb', 'data-image', 'data-href',
                'data-large', 'data-medium', 'data-small'
            ]
            
            for attr in attrs_to_check:
                value = img.get(attr)
                if value:
                    if attr in ['srcset', 'data-srcset']:
                        for item in value.split(','):
                            item = item.strip()
                            if item:
                                parts = item.split()
                                if parts:
                                    url = parts[0]
                                    if url not in images:
                                        images.append(url)
                    else:
                        if value not in images:
                            images.append(value)
        
        class_patterns = ['main_img', 'img-hover', 'currentImg', 'preview']
        for class_name in class_patterns:
            for img in soup.find_all('img', class_=class_name):
                for attr in ['src', 'data-src', 'data-lazy']:
                    value = img.get(attr)
                    if value and value not in images:
                        images.append(value)
        
        return list(set(images))
    
    @staticmethod
    def extract_from_baidu_json(json_text, logger=None):
        images = []
        try:
            data = json.loads(json_text)
            
            if 'data' in data:
                if logger:
                    logger.debug(f"JSON中找到 {len(data['data'])} 个图片数据项")
                
                for item in data['data']:
                    url_fields = ['thumbURL', 'objURL', 'hoverURL', 'middleURL', 'pageURL', 'fromURL', 'url']
                    for field in url_fields:
                        if field in item and item[field]:
                            url = item[field]
                            url = url.replace('\\/', '/')
                            if url not in images:
                                images.append(url)
            
            return images
        except json.JSONDecodeError as e:
            if logger:
                logger.error(f"JSON解析失败: {e}")
            return []
    
    @staticmethod
    def extract_from_bing(html, logger=None):
        images = []
        
        soup = BeautifulSoup(html, 'lxml')
        
        for a_tag in soup.find_all('a', class_='iusc'):
            m = a_tag.get('m')
            if m:
                try:
                    data = json.loads(m)
                    url_fields = ['murl', 'turl', 'imgurl', 'purl']
                    for field in url_fields:
                        if field in data and data[field]:
                            url = data[field]
                            if url not in images:
                                images.append(url)
                except:
                    pass
        
        patterns = [
            r'"murl"\s*:\s*"(http[^"]+)"',
            r'"turl"\s*:\s*"(http[^"]+)"',
            r'"imgurl"\s*:\s*"(http[^"]+)"',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html)
            for match in matches:
                url = match.replace('\\/', '/')
                if url not in images:
                    images.append(url)
        
        url_pattern = r'(https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|gif|bmp|webp))'
        matches = re.findall(url_pattern, html, re.IGNORECASE)
        for match in matches:
            if match not in images:
                images.append(match)
        
        return list(set(images))
    
    @staticmethod
    def extract_from_generic(html, page_url, logger=None):
        images = []
        soup = BeautifulSoup(html, 'lxml')
        
        img_tags = soup.find_all('img')
        if logger:
            logger.debug(f"找到 {len(img_tags)} 个img标签")
        
        for img_tag in img_tags:
            attrs = [
                'src', 'data-src', 'data-lazy', 'data-original',
                'data-srcset', 'srcset', 'data-url', 'data-imgurl'
            ]
            
            for attr in attrs:
                value = img_tag.get(attr)
                if value:
                    if attr in ['srcset', 'data-srcset']:
                        for item in value.split(','):
                            item = item.strip()
                            if item:
                                parts = item.split()
                                if parts:
                                    img_url = parts[0]
                                    full_url = urljoin(page_url, img_url)
                                    if full_url not in images:
                                        images.append(full_url)
                    else:
                        full_url = urljoin(page_url, value)
                        if full_url not in images:
                            images.append(full_url)
        
        url_pattern = r'(https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|gif|bmp|webp|svg))'
        matches = re.findall(url_pattern, html, re.IGNORECASE)
        for match in matches:
            if match not in images:
                images.append(match)
        
        return list(set(images))


class ImageCrawler:
    def __init__(self, base_url, keywords, max_images, save_dir, 
                 user_agent=None, delay=1.0, log_callback=None,
                 search_engine='auto', max_pages=10, debug_mode=True,
                 deduplicate_method='md5', phash_threshold=5,
                 verify_ssl=True):
        self.base_url = base_url
        self.keywords = [k.strip() for k in keywords.split(',') if k.strip()]
        self.max_images = max_images
        self.save_dir = save_dir
        self.downloaded_count = 0
        self.found_urls = set()
        self.is_running = True
        self.delay = delay
        self.search_engine = search_engine
        self.max_pages = max_pages
        self.debug_mode = debug_mode
        self.deduplicate_method = deduplicate_method
        self.phash_threshold = phash_threshold
        self.verify_ssl = verify_ssl
        
        self.logger = DebugLogger(log_callback, debug_mode)
        self.deduplicator = ImageDeduplicator(self.logger)
        
        if not verify_ssl:
            self.logger.info("[SSL] SSL证书验证已禁用（verify=False）")
        
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/123.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        ]
        
        self.headers = {
            'User-Agent': user_agent or random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'Referer': base_url
        }

    def _rotate_user_agent(self):
        new_ua = random.choice(self.user_agents)
        self.headers['User-Agent'] = new_ua
        if self.debug_mode:
            self.logger.debug(f"切换User-Agent: {new_ua[:50]}...")

    def _make_request(self, url, timeout=20, stream=False, is_image=False):
        try:
            time.sleep(self.delay)
            
            if not is_image:
                self._rotate_user_agent()
            
            self.headers['Referer'] = url
            
            if self.debug_mode:
                self.logger.debug(f"请求URL: {url[:80]}{'...' if len(url) > 80 else ''}")
            
            if stream:
                response = requests.get(
                    url, 
                    headers=self.headers, 
                    timeout=timeout, 
                    stream=True,
                    allow_redirects=True,
                    verify=self.verify_ssl
                )
            else:
                response = requests.get(
                    url, 
                    headers=self.headers, 
                    timeout=timeout,
                    allow_redirects=True,
                    verify=self.verify_ssl
                )
            
            if self.debug_mode:
                self.logger.debug(f"响应状态码: {response.status_code}")
                if 'Content-Type' in response.headers:
                    self.logger.debug(f"Content-Type: {response.headers['Content-Type']}")
            
            response.raise_for_status()
            return response
            
        except requests.RequestException as e:
            self.logger.error(f"请求失败: {str(e)[:100]}")
            return None

    def _is_valid_image(self, img_url):
        parsed = urlparse(img_url)
        
        if parsed.scheme not in ('http', 'https'):
            return False
        
        ext = os.path.splitext(parsed.path)[1].lower()
        valid_exts = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico')
        
        if ext in valid_exts:
            return True
        
        if ext == '' or '?url=' in img_url or 'url=' in img_url or 'imgurl=' in img_url:
            return True
        
        if 'image' in img_url.lower() or 'photo' in img_url.lower() or 'pic' in img_url.lower():
            return True
        
        return False

    def _extract_images_from_page(self, html, page_url, engine='generic'):
        images = []
        
        if engine == 'baidu':
            if self.debug_mode:
                self.logger.debug("使用百度图片提取器...")
            
            try:
                json_images = ImageExtractor.extract_from_baidu_json(html, self.logger)
                if json_images:
                    images.extend(json_images)
                    self.logger.info(f"从JSON数据提取了 {len(json_images)} 个图片URL")
            except Exception as e:
                self.logger.error(f"JSON提取失败: {e}")
            
            html_images = ImageExtractor.extract_from_baidu_html(html, self.logger)
            if html_images:
                images.extend(html_images)
                self.logger.info(f"从HTML提取了 {len(html_images)} 个图片URL")
        
        elif engine == 'bing':
            if self.debug_mode:
                self.logger.debug("使用必应图片提取器...")
            images = ImageExtractor.extract_from_bing(html, self.logger)
        
        else:
            if self.debug_mode:
                self.logger.debug("使用通用图片提取器...")
            images = ImageExtractor.extract_from_generic(html, page_url, self.logger)
        
        if self.debug_mode:
            self.logger.debug(f"总共提取到 {len(images)} 个图片URL（去重前）")
        
        valid_images = []
        for img_url in images:
            if not img_url:
                continue
            
            if img_url in self.found_urls:
                continue
            
            if not self._is_valid_image(img_url):
                continue
            
            self.found_urls.add(img_url)
            valid_images.append(img_url)
        
        if self.debug_mode:
            self.logger.info(f"验证后剩余 {len(valid_images)} 个有效图片URL")
        
        return valid_images

    def _download_image(self, img_url):
        try:
            if self.debug_mode:
                self.logger.debug(f"正在下载: {img_url[:60]}...")
            
            response = self._make_request(img_url, timeout=30, stream=True, is_image=True)
            if not response:
                return False
            
            content_type = response.headers.get('Content-Type', '')
            if self.debug_mode:
                self.logger.debug(f"图片Content-Type: {content_type}")
            
            if not content_type.startswith('image/'):
                if 'application/octet-stream' not in content_type and 'binary' not in content_type.lower():
                    self.logger.debug(f"跳过非图片内容: {content_type}")
                    return False
            
            content = response.content
            
            if len(content) < 100:
                self.logger.debug(f"图片内容过小 ({len(content)} bytes)，跳过")
                return False
            
            try:
                img = Image.open(BytesIO(content))
                if self.debug_mode:
                    self.logger.debug(f"图片格式: {img.format}, 尺寸: {img.size}")
            except Exception as e:
                self.logger.error(f"图片格式验证失败: {e}")
                return False
            
            if self.deduplicate_method != 'none':
                if self.deduplicator.is_duplicate(
                    content=content, 
                    img=img, 
                    method=self.deduplicate_method,
                    phash_threshold=self.phash_threshold
                ):
                    self.deduplicator.duplicate_count += 1
                    method_name = {
                        'md5': 'MD5',
                        'phash': 'pHash',
                        'both': 'MD5+pHash'
                    }.get(self.deduplicate_method, self.deduplicate_method)
                    self.logger.info(f"[去重] 检测到重复图片 ({method_name})，已跳过 (累计: {self.deduplicator.duplicate_count})")
                    return False
            
            ext = img.format.lower() if img.format else 'jpg'
            if ext == 'jpeg':
                ext = 'jpg'
            
            if self.keywords:
                safe_keyword = re.sub(r'[^\w\s\u4e00-\u9fa5-]', '', self.keywords[0])
                safe_keyword = safe_keyword[:15] if safe_keyword else 'image'
                safe_keyword = safe_keyword.replace(' ', '_')
            else:
                safe_keyword = 'image'
            
            url_hash = hashlib.md5(img_url.encode()).hexdigest()[:8]
            filename = f"{safe_keyword}_{self.downloaded_count + 1}_{url_hash}.{ext}"
            filepath = os.path.join(self.save_dir, filename)
            
            counter = 1
            while os.path.exists(filepath):
                filename = f"{safe_keyword}_{self.downloaded_count + 1}_{counter}_{url_hash}.{ext}"
                filepath = os.path.join(self.save_dir, filename)
                counter += 1
            
            try:
                with open(filepath, 'wb') as f:
                    f.write(content)
            except Exception as e:
                try:
                    img.save(filepath)
                except Exception as e2:
                    self.logger.error(f"保存图片失败: {e2}")
                    return False
            
            self.downloaded_count += 1
            self.logger.success(f"已下载: {filename} ({self.downloaded_count}/{self.max_images})")
            return True
            
        except Exception as e:
            self.logger.error(f"下载图片异常: {str(e)[:80]}")
            return False

    def _search_with_keyword(self, keyword):
        engine = SearchEngineAdapter.get_engine_from_url(self.base_url)
        
        if self.search_engine != 'auto':
            engine = self.search_engine
        
        self.logger.info(f"=" * 60)
        self.logger.info(f"开始搜索关键词: {keyword}")
        self.logger.info(f"使用搜索引擎模式: {engine}")
        self.logger.info("=" * 60)
        
        for page in range(1, self.max_pages + 1):
            if not self.is_running:
                self.logger.info("用户请求停止，正在退出...")
                break
            
            if self.downloaded_count >= self.max_images:
                self.logger.info(f"已达到目标图片数 ({self.max_images})，停止搜索")
                break
            
            if engine == 'baidu':
                search_url = SearchEngineAdapter.build_baidu_image_url_v2(keyword, page)
                search_url_ajax = SearchEngineAdapter.build_baidu_image_ajax_url(keyword, page)
            elif engine == 'bing':
                search_url = SearchEngineAdapter.build_bing_image_url(keyword, page)
                search_url_ajax = None
            elif engine == 'google':
                search_url = SearchEngineAdapter.build_google_image_url(keyword, page)
                search_url_ajax = None
            else:
                search_url = self.base_url
                search_url_ajax = None
            
            self.logger.info(f"\n--- 正在访问第 {page} 页 ---")
            self.logger.info(f"搜索URL: {search_url[:100]}...")
            
            if search_url_ajax and engine == 'baidu':
                self.logger.info(f"尝试AJAX接口: {search_url_ajax[:100]}...")
                response_ajax = self._make_request(search_url_ajax)
                if response_ajax:
                    self.headers['Referer'] = search_url_ajax
                    text_ajax = response_ajax.text
                    
                    img_urls_ajax = self._extract_images_from_page(text_ajax, search_url_ajax, engine)
                    self.logger.info(f"AJAX接口找到 {len(img_urls_ajax)} 张图片")
                    
                    for img_url in img_urls_ajax:
                        if not self.is_running:
                            break
                        if self.downloaded_count >= self.max_images:
                            break
                        self._download_image(img_url)
                    
                    if self.downloaded_count >= self.max_images:
                        break
            
            response = self._make_request(search_url)
            if not response:
                self.logger.error(f"第 {page} 页访问失败，跳过")
                continue
            
            self.headers['Referer'] = search_url
            html = response.text
            
            if self.debug_mode:
                debug_file = os.path.join(self.save_dir, f"debug_page_{page}.html")
                try:
                    with open(debug_file, 'w', encoding='utf-8') as f:
                        f.write(html)
                    self.logger.debug(f"已保存调试HTML到: {debug_file}")
                except Exception as e:
                    self.logger.error(f"保存调试文件失败: {e}")
            
            img_urls = self._extract_images_from_page(html, search_url, engine)
            self.logger.info(f"在第 {page} 页找到 {len(img_urls)} 张有效图片")
            
            if len(img_urls) == 0:
                self.logger.warning(f"第 {page} 页没有找到新图片，尝试继续下一页...")
                continue
            
            downloaded_this_page = 0
            for img_url in img_urls:
                if not self.is_running:
                    break
                
                if self.downloaded_count >= self.max_images:
                    break
                
                if self._download_image(img_url):
                    downloaded_this_page += 1
            
            self.logger.info(f"第 {page} 页成功下载 {downloaded_this_page} 张图片")

    def start(self):
        self.logger.info("=" * 60)
        self.logger.info("图片采集工具启动")
        self.logger.info("=" * 60)
        self.logger.info(f"目标网站: {self.base_url}")
        self.logger.info(f"关键词: {', '.join(self.keywords) if self.keywords else '无'}")
        self.logger.info(f"目标图片数: {self.max_images}")
        self.logger.info(f"保存目录: {self.save_dir}")
        self.logger.info(f"请求延迟: {self.delay} 秒")
        self.logger.info(f"爬取页数: {self.max_pages} 页")
        self.logger.info("=" * 60)
        
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir, exist_ok=True)
            self.logger.info(f"已创建保存目录: {self.save_dir}")
        
        if self.keywords:
            for keyword in self.keywords:
                if not self.is_running:
                    break
                
                if self.downloaded_count >= self.max_images:
                    break
                
                self._search_with_keyword(keyword)
                
                if self.downloaded_count >= self.max_images:
                    self.logger.info(f"已完成目标图片数 ({self.max_images})")
                    break
        else:
            self.logger.info("没有指定关键词，将直接爬取目标页面...")
            engine = SearchEngineAdapter.get_engine_from_url(self.base_url)
            
            response = self._make_request(self.base_url)
            if response:
                html = response.text
                img_urls = self._extract_images_from_page(html, self.base_url, engine)
                self.logger.info(f"在页面中找到 {len(img_urls)} 张图片")
                
                for img_url in img_urls:
                    if not self.is_running:
                        break
                    if self.downloaded_count >= self.max_images:
                        break
                    self._download_image(img_url)
        
        self.logger.info("=" * 60)
        self.logger.info(f"爬取完成! 共下载 {self.downloaded_count} 张图片")
        self.logger.info("=" * 60)
        return self.downloaded_count

    def stop(self):
        self.is_running = False
        self.logger.info("正在停止爬取...")


class ImageCrawlerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("图片采集工具 - 增强版 v2.0")
        self.root.geometry("950x750")
        self.root.resizable(True, True)
        
        self.crawler = None
        self.crawl_thread = None
        
        self._create_ui()
    
    def _create_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(10, weight=1)
        
        row = 0
        
        title_frame = ttk.Frame(main_frame)
        title_frame.grid(row=row, column=0, columnspan=2, pady=10)
        title_label = ttk.Label(
            title_frame, 
            text="🐱 图片采集工具 - 输入关键词即可搜索下载相关图片",
            font=('Arial', 14, 'bold')
        )
        title_label.pack()
        row += 1
        
        info_frame = ttk.LabelFrame(main_frame, text="使用说明", padding="5")
        info_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        info_text = (
            "1. 选择搜索引擎，输入关键词（如：猫咪、风景、汽车），多个关键词用逗号分隔\n"
            "2. 程序会自动构造搜索URL并提取图片，无需手动输入搜索页面\n"
            "3. 建议使用百度图片或必应图片，成功率较高\n"
            "4. 调试模式会保存HTML到本地，方便排查问题"
        )
        info_label = ttk.Label(info_frame, text=info_text, wraplength=900)
        info_label.pack(fill=tk.X)
        row += 1
        
        ttk.Label(main_frame, text="搜索引擎:").grid(row=row, column=0, sticky=tk.W, pady=5)
        engine_frame = ttk.Frame(main_frame)
        engine_frame.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)
        
        self.engine_var = tk.StringVar(value='baidu')
        engines = [
            ("百度图片 (推荐)", 'baidu'),
            ("必应图片", 'bing'),
            ("自动检测", 'auto'),
            ("通用网站", 'generic')
        ]
        
        for text, value in engines:
            ttk.Radiobutton(engine_frame, text=text, value=value, variable=self.engine_var).pack(side=tk.LEFT, padx=10)
        row += 1
        
        ttk.Label(main_frame, text="目标网站 (通用模式用):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.url_entry = ttk.Entry(main_frame, width=60)
        self.url_entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
        self.url_entry.insert(0, "https://image.baidu.com")
        
        url_hint = ttk.Label(main_frame, text="(选择百度/必应后，程序会自动构造搜索URL，此URL仅用于通用模式)", font=('Arial', 8))
        url_hint.grid(row=row+1, column=1, sticky=tk.W, padx=5)
        row += 2
        
        ttk.Label(main_frame, text="关键词 (逗号分隔):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.keywords_entry = ttk.Entry(main_frame, width=60, font=('Arial', 11))
        self.keywords_entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
        self.keywords_entry.insert(0, "猫咪,风景,汽车")
        
        keyword_hint = ttk.Label(main_frame, text="🔴 必须填写关键词！例如: 猫咪,白菜,小狗,风景,汽车", font=('Arial', 9, 'bold'), foreground='red')
        keyword_hint.grid(row=row+1, column=1, sticky=tk.W, padx=5)
        row += 2
        
        options_frame = ttk.LabelFrame(main_frame, text="高级选项", padding="5")
        options_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        opt_row = 0
        
        ttk.Label(options_frame, text="图片数量:").grid(row=opt_row, column=0, sticky=tk.W, pady=5, padx=5)
        self.count_var = tk.IntVar(value=20)
        self.count_spinbox = ttk.Spinbox(options_frame, from_=1, to=1000, textvariable=self.count_var, width=12)
        self.count_spinbox.grid(row=opt_row, column=1, sticky=tk.W, pady=5, padx=5)
        
        ttk.Label(options_frame, text="爬取页数:").grid(row=opt_row, column=2, sticky=tk.W, pady=5, padx=20)
        self.pages_var = tk.IntVar(value=5)
        self.pages_spinbox = ttk.Spinbox(options_frame, from_=1, to=50, textvariable=self.pages_var, width=12)
        self.pages_spinbox.grid(row=opt_row, column=3, sticky=tk.W, pady=5, padx=5)
        
        ttk.Label(options_frame, text="请求延迟(秒):").grid(row=opt_row, column=4, sticky=tk.W, pady=5, padx=20)
        self.delay_var = tk.DoubleVar(value=1.5)
        self.delay_spinbox = ttk.Spinbox(options_frame, from_=0.5, to=10.0, increment=0.1, textvariable=self.delay_var, width=12)
        self.delay_spinbox.grid(row=opt_row, column=5, sticky=tk.W, pady=5, padx=5)
        
        self.debug_var = tk.BooleanVar(value=True)
        self.debug_check = ttk.Checkbutton(options_frame, text="调试模式(保存HTML)", variable=self.debug_var)
        self.debug_check.grid(row=opt_row, column=6, sticky=tk.W, pady=5, padx=20)
        
        opt_row += 1
        
        ttk.Label(options_frame, text="去重方式:").grid(row=opt_row, column=0, sticky=tk.W, pady=5, padx=5)
        dedup_frame = ttk.Frame(options_frame)
        dedup_frame.grid(row=opt_row, column=1, columnspan=3, sticky=tk.W, pady=5, padx=5)
        
        self.dedup_var = tk.StringVar(value='md5')
        dedup_methods = [
            ("不启用", 'none'),
            ("MD5 (精确)", 'md5'),
            ("pHash (感知)", 'phash'),
            ("MD5+pHash (双重)", 'both')
        ]
        
        for text, value in dedup_methods:
            ttk.Radiobutton(dedup_frame, text=text, value=value, variable=self.dedup_var).pack(side=tk.LEFT, padx=10)
        
        ttk.Label(options_frame, text="pHash阈值:").grid(row=opt_row, column=4, sticky=tk.W, pady=5, padx=20)
        self.phash_threshold_var = tk.IntVar(value=5)
        self.phash_threshold_spinbox = ttk.Spinbox(options_frame, from_=0, to=20, textvariable=self.phash_threshold_var, width=10)
        self.phash_threshold_spinbox.grid(row=opt_row, column=5, sticky=tk.W, pady=5, padx=5)
        
        phash_hint = ttk.Label(options_frame, text="(越小越严格，建议3-8)", font=('Arial', 8))
        phash_hint.grid(row=opt_row, column=6, sticky=tk.W, padx=5)
        
        opt_row += 1
        
        ttk.Label(options_frame, text="保存目录:").grid(row=opt_row, column=0, sticky=tk.W, pady=5, padx=5)
        save_frame = ttk.Frame(options_frame)
        save_frame.grid(row=opt_row, column=1, columnspan=6, sticky=(tk.W, tk.E), pady=5, padx=5)
        save_frame.columnconfigure(0, weight=1)
        
        self.save_dir_var = tk.StringVar(value=os.path.join(os.getcwd(), "downloads"))
        self.save_dir_entry = ttk.Entry(save_frame, textvariable=self.save_dir_var)
        self.save_dir_entry.grid(row=0, column=0, sticky=(tk.W, tk.E))
        self.browse_button = ttk.Button(save_frame, text="浏览", command=self._browse_save_dir)
        self.browse_button.grid(row=0, column=1, padx=5)
        
        opt_row += 1
        
        ssl_frame = ttk.Frame(options_frame)
        ssl_frame.grid(row=opt_row, column=0, columnspan=7, sticky=tk.W, pady=5, padx=5)
        
        self.verify_ssl_var = tk.BooleanVar(value=True)
        self.verify_ssl_check = ttk.Checkbutton(
            ssl_frame, 
            text="SSL证书验证 (禁用后可访问证书有问题的HTTPS站点)", 
            variable=self.verify_ssl_var
        )
        self.verify_ssl_check.pack(side=tk.LEFT, padx=5)
        
        ssl_hint = ttk.Label(ssl_frame, text="(默认启用，访问内网/自签名证书站点可禁用)", font=('Arial', 8), foreground='gray')
        ssl_hint.pack(side=tk.LEFT, padx=10)
        
        row += 1
        
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=2, pady=15)
        
        self.start_button = ttk.Button(button_frame, text="🚀 开始采集", command=self._start_crawl, width=15)
        self.start_button.pack(side=tk.LEFT, padx=10)
        
        self.stop_button = ttk.Button(button_frame, text="⏹ 停止采集", command=self._stop_crawl, state=tk.DISABLED, width=15)
        self.stop_button.pack(side=tk.LEFT, padx=10)
        
        self.open_folder_button = ttk.Button(button_frame, text="📂 打开保存目录", command=self._open_save_folder, width=15)
        self.open_folder_button.pack(side=tk.LEFT, padx=10)
        
        row += 1
        
        ttk.Label(main_frame, text="日志输出:").grid(row=row, column=0, sticky=tk.NW, pady=5)
        log_frame = ttk.Frame(main_frame)
        log_frame.grid(row=row, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5, padx=5)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame, 
            wrap=tk.WORD, 
            height=15,
            font=('Consolas', 9)
        )
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.log_text.config(state=tk.DISABLED)
        
        row += 1
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100, mode='determinate')
        self.progress_bar.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        self.progress_label = ttk.Label(main_frame, text="进度: 0/0 张图片", font=('Arial', 10))
        self.progress_label.grid(row=row+1, column=0, columnspan=2, pady=5)
    
    def _browse_save_dir(self):
        directory = filedialog.askdirectory(initialdir=self.save_dir_var.get())
        if directory:
            self.save_dir_var.set(directory)
    
    def _open_save_folder(self):
        folder = self.save_dir_var.get()
        if os.path.exists(folder):
            os.startfile(folder)
        else:
            messagebox.showinfo("提示", "保存目录不存在，请先运行采集任务")
    
    def _log_message(self, message):
        self.root.after(0, self._append_log, message)
    
    def _append_log(self, message):
        self.log_text.config(state=tk.NORMAL)
        
        tags = ['[INFO]', '[DEBUG]', '[ERROR]', '[✓]']
        for tag in tags:
            if message.startswith(tag):
                if tag == '[ERROR]':
                    self.log_text.insert(tk.END, message + "\n", 'error')
                elif tag == '[✓]':
                    self.log_text.insert(tk.END, message + "\n", 'success')
                elif tag == '[DEBUG]':
                    self.log_text.insert(tk.END, message + "\n", 'debug')
                else:
                    self.log_text.insert(tk.END, message + "\n")
                break
        else:
            self.log_text.insert(tk.END, message + "\n")
        
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def _configure_tags(self):
        self.log_text.tag_config('error', foreground='red')
        self.log_text.tag_config('success', foreground='green')
        self.log_text.tag_config('debug', foreground='gray')
    
    def _update_progress(self):
        if self.crawler:
            current = self.crawler.downloaded_count
            total = self.crawler.max_images
            self.progress_label.config(text=f"进度: {current}/{total} 张图片")
            if total > 0:
                self.progress_var.set((current / total) * 100)
            
            if self.crawl_thread and self.crawl_thread.is_alive():
                self.root.after(100, self._update_progress)
    
    def _start_crawl(self):
        url = self.url_entry.get().strip()
        keywords = self.keywords_entry.get().strip()
        max_images = self.count_var.get()
        save_dir = self.save_dir_var.get()
        delay = self.delay_var.get()
        engine = self.engine_var.get()
        max_pages = self.pages_var.get()
        debug_mode = self.debug_var.get()
        deduplicate_method = self.dedup_var.get()
        phash_threshold = self.phash_threshold_var.get()
        verify_ssl = self.verify_ssl_var.get()
        
        if not keywords:
            messagebox.showwarning("⚠️ 缺少关键词", "请输入关键词！\n\n例如: 猫咪,白菜,小狗,风景,汽车\n\n关键词用于搜索相关图片，必须填写。")
            return
        
        if not save_dir:
            messagebox.showerror("错误", "请选择保存目录")
            return
        
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.progress_var.set(0)
        
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self._configure_tags()
        self.log_text.config(state=tk.DISABLED)
        
        self.crawler = ImageCrawler(
            base_url=url,
            keywords=keywords,
            max_images=max_images,
            save_dir=save_dir,
            delay=delay,
            log_callback=self._log_message,
            search_engine=engine,
            max_pages=max_pages,
            debug_mode=debug_mode,
            deduplicate_method=deduplicate_method,
            phash_threshold=phash_threshold,
            verify_ssl=verify_ssl
        )
        
        def run_crawl():
            try:
                self.crawler.start()
            except Exception as e:
                self._log_message(f"[ERROR] 发生致命错误: {e}")
                import traceback
                self._log_message(f"[DEBUG] {traceback.format_exc()}")
            finally:
                self.root.after(0, self._crawl_finished)
        
        self.crawl_thread = threading.Thread(target=run_crawl, daemon=True)
        self.crawl_thread.start()
        self._update_progress()
    
    def _stop_crawl(self):
        if self.crawler:
            self.crawler.stop()
        self.stop_button.config(state=tk.DISABLED)
    
    def _crawl_finished(self):
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        if self.crawler:
            count = self.crawler.downloaded_count
            if count > 0:
                messagebox.showinfo("✅ 采集完成", f"采集完成！\n\n共下载 {count} 张图片\n保存目录: {self.save_dir_var.get()}")
            else:
                messagebox.showwarning("⚠️ 未下载图片", 
                    "没有下载到任何图片。\n\n可能的原因：\n"
                    "1. 搜索引擎反爬虫机制\n"
                    "2. 网络连接问题\n"
                    "3. 关键词可能过于特殊\n\n"
                    "建议：\n"
                    "1. 增加请求延迟时间\n"
                    "2. 尝试不同的搜索引擎\n"
                    "3. 检查网络连接\n"
                    "4. 开启调试模式查看HTML内容")


def main():
    root = tk.Tk()
    app = ImageCrawlerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
