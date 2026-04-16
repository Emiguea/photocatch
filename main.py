import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import re
import time
import json
import random
from urllib.parse import urljoin, urlparse, quote, unquote
import requests
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO


class SearchEngineAdapter:
    @staticmethod
    def build_baidu_image_url(keyword, page=1):
        pn = (page - 1) * 30
        return f"https://image.baidu.com/search/index?tn=baiduimage&word={quote(keyword)}&pn={pn}"
    
    @staticmethod
    def build_bing_image_url(keyword, page=1):
        first = (page - 1) * 35 + 1
        return f"https://www.bing.com/images/search?q={quote(keyword)}&first={first}"
    
    @staticmethod
    def build_google_image_url(keyword, page=1):
        start = (page - 1) * 20
        return f"https://www.google.com/search?q={quote(keyword)}&tbm=isch&start={start}"
    
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
    def extract_from_baidu(html):
        images = []
        pattern = r'"thumbURL":"(http[^"]+)"'
        matches = re.findall(pattern, html)
        for match in matches:
            url = match.replace('\\/', '/')
            images.append(url)
        
        pattern2 = r'"objURL":"(http[^"]+)"'
        matches2 = re.findall(pattern2, html)
        for match in matches2:
            url = match.replace('\\/', '/')
            images.append(url)
        
        soup = BeautifulSoup(html, 'lxml')
        for img in soup.find_all('img', class_='main_img'):
            src = img.get('data-src') or img.get('src')
            if src:
                images.append(src)
        
        return list(set(images))
    
    @staticmethod
    def extract_from_bing(html):
        images = []
        soup = BeautifulSoup(html, 'lxml')
        
        for a_tag in soup.find_all('a', class_='iusc'):
            m = a_tag.get('m')
            if m:
                try:
                    data = json.loads(m)
                    if 'murl' in data:
                        images.append(data['murl'])
                    elif 'turl' in data:
                        images.append(data['turl'])
                except:
                    pass
        
        pattern = r'"murl":"(http[^"]+)"'
        matches = re.findall(pattern, html)
        for match in matches:
            url = match.replace('\\/', '/')
            images.append(url)
        
        return list(set(images))
    
    @staticmethod
    def extract_from_generic(html, page_url):
        images = []
        soup = BeautifulSoup(html, 'lxml')
        
        for img_tag in soup.find_all('img'):
            src = img_tag.get('src', '')
            data_src = img_tag.get('data-src', '')
            data_lazy = img_tag.get('data-lazy', '')
            data_original = img_tag.get('data-original', '')
            data_srcset = img_tag.get('data-srcset', '')
            srcset = img_tag.get('srcset', '')
            
            img_urls_to_check = []
            
            if src:
                img_urls_to_check.append(src)
            if data_src:
                img_urls_to_check.append(data_src)
            if data_lazy:
                img_urls_to_check.append(data_lazy)
            if data_original:
                img_urls_to_check.append(data_original)
            
            if data_srcset:
                for item in data_srcset.split(','):
                    item = item.strip()
                    if item:
                        parts = item.split()
                        if parts:
                            img_urls_to_check.append(parts[0])
            
            if srcset:
                for item in srcset.split(','):
                    item = item.strip()
                    if item:
                        parts = item.split()
                        if parts:
                            img_urls_to_check.append(parts[0])
            
            for img_url in img_urls_to_check:
                if img_url and img_url not in images:
                    full_url = urljoin(page_url, img_url)
                    images.append(full_url)
        
        return list(set(images))


class ImageCrawler:
    def __init__(self, base_url, keywords, max_images, save_dir, 
                 user_agent=None, delay=1.0, log_callback=None,
                 search_engine='auto', max_pages=10):
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
        
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36'
        ]
        
        self.headers = {
            'User-Agent': user_agent or random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': base_url
        }
        
        self.log_callback = log_callback

    def log(self, message):
        if self.log_callback:
            self.log_callback(message)

    def _rotate_user_agent(self):
        self.headers['User-Agent'] = random.choice(self.user_agents)

    def _make_request(self, url, timeout=15, stream=False):
        try:
            time.sleep(self.delay)
            self._rotate_user_agent()
            
            if stream:
                response = requests.get(url, headers=self.headers, timeout=timeout, stream=True)
            else:
                response = requests.get(url, headers=self.headers, timeout=timeout)
            
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            self.log(f"请求失败: {e}")
            return None

    def _is_valid_image(self, img_url):
        parsed = urlparse(img_url)
        if parsed.scheme not in ('http', 'https'):
            return False
        
        ext = os.path.splitext(parsed.path)[1].lower()
        valid_exts = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg')
        
        if ext in valid_exts:
            return True
        
        if ext == '' or '?url=' in img_url or 'url=' in img_url:
            return True
        
        return False

    def _extract_images_from_page(self, html, page_url, engine='generic'):
        images = []
        
        if engine == 'baidu':
            images = ImageExtractor.extract_from_baidu(html)
        elif engine == 'bing':
            images = ImageExtractor.extract_from_bing(html)
        else:
            images = ImageExtractor.extract_from_generic(html, page_url)
        
        valid_images = []
        for img_url in images:
            if img_url and img_url not in self.found_urls:
                if self._is_valid_image(img_url):
                    self.found_urls.add(img_url)
                    valid_images.append(img_url)
        
        return valid_images

    def _download_image(self, img_url):
        try:
            response = self._make_request(img_url, timeout=20, stream=True)
            if not response:
                return False
            
            content_type = response.headers.get('Content-Type', '')
            if not content_type.startswith('image/'):
                if 'application/octet-stream' not in content_type:
                    return False
            
            content = response.content
            
            try:
                img = Image.open(BytesIO(content))
            except Exception as e:
                self.log(f"图片格式验证失败: {e}")
                return False
            
            ext = img.format.lower() if img.format else 'jpg'
            if ext == 'jpeg':
                ext = 'jpg'
            
            if self.keywords:
                safe_keyword = re.sub(r'[^\w\s-]', '', self.keywords[0])
                safe_keyword = safe_keyword[:20] if safe_keyword else 'image'
            else:
                safe_keyword = 'image'
            
            filename = f"{safe_keyword}_{self.downloaded_count + 1}.{ext}"
            filepath = os.path.join(self.save_dir, filename)
            
            counter = 1
            while os.path.exists(filepath):
                filename = f"{safe_keyword}_{self.downloaded_count + 1}_{counter}.{ext}"
                filepath = os.path.join(self.save_dir, filename)
                counter += 1
            
            try:
                with open(filepath, 'wb') as f:
                    f.write(content)
            except Exception as e:
                try:
                    img.save(filepath)
                except Exception as e2:
                    self.log(f"保存图片失败: {e2}")
                    return False
            
            self.downloaded_count += 1
            self.log(f"已下载: {filename} ({self.downloaded_count}/{self.max_images})")
            return True
            
        except Exception as e:
            self.log(f"下载图片失败 {img_url}: {e}")
            return False

    def _search_with_keyword(self, keyword):
        engine = SearchEngineAdapter.get_engine_from_url(self.base_url)
        
        if self.search_engine != 'auto':
            engine = self.search_engine
        
        self.log(f"使用搜索引擎: {engine}")
        self.log(f"搜索关键词: {keyword}")
        
        all_images = []
        
        for page in range(1, self.max_pages + 1):
            if not self.is_running:
                break
            
            if self.downloaded_count >= self.max_images:
                break
            
            if engine == 'baidu':
                search_url = SearchEngineAdapter.build_baidu_image_url(keyword, page)
            elif engine == 'bing':
                search_url = SearchEngineAdapter.build_bing_image_url(keyword, page)
            elif engine == 'google':
                search_url = SearchEngineAdapter.build_google_image_url(keyword, page)
            else:
                search_url = self.base_url
            
            self.log(f"正在访问第 {page} 页: {search_url}")
            self.headers['Referer'] = search_url
            
            response = self._make_request(search_url)
            if not response:
                continue
            
            html = response.text
            
            img_urls = self._extract_images_from_page(html, search_url, engine)
            self.log(f"在第 {page} 页找到 {len(img_urls)} 张图片")
            
            for img_url in img_urls:
                if not self.is_running:
                    break
                
                if self.downloaded_count >= self.max_images:
                    break
                
                self._download_image(img_url)
            
            if len(img_urls) == 0:
                self.log(f"第 {page} 页没有找到新图片，停止翻页")
                break

    def start(self):
        self.log(f"开始爬取...")
        self.log(f"目标网站: {self.base_url}")
        self.log(f"关键词: {', '.join(self.keywords) if self.keywords else '无'}")
        self.log(f"最大图片数: {self.max_images}")
        self.log(f"保存目录: {self.save_dir}")
        
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir, exist_ok=True)
        
        if self.keywords:
            for keyword in self.keywords:
                if not self.is_running:
                    break
                
                if self.downloaded_count >= self.max_images:
                    break
                
                self.log(f"=" * 50)
                self.log(f"开始搜索关键词: {keyword}")
                self.log(f"=" * 50)
                
                self._search_with_keyword(keyword)
                
                if self.downloaded_count >= self.max_images:
                    break
        else:
            self.log(f"没有指定关键词，将直接爬取目标页面...")
            engine = SearchEngineAdapter.get_engine_from_url(self.base_url)
            
            response = self._make_request(self.base_url)
            if response:
                html = response.text
                img_urls = self._extract_images_from_page(html, self.base_url, engine)
                self.log(f"在页面中找到 {len(img_urls)} 张图片")
                
                for img_url in img_urls:
                    if not self.is_running:
                        break
                    
                    if self.downloaded_count >= self.max_images:
                        break
                    
                    self._download_image(img_url)
        
        self.log(f"爬取完成! 共下载 {self.downloaded_count} 张图片")
        return self.downloaded_count

    def stop(self):
        self.is_running = False
        self.log("正在停止爬取...")


class ImageCrawlerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("图片采集工具 - 关键词搜索版")
        self.root.geometry("900x700")
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
        main_frame.rowconfigure(9, weight=1)
        
        row = 0
        
        info_frame = ttk.LabelFrame(main_frame, text="使用说明", padding="5")
        info_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        info_text = (
            "1. 选择搜索引擎后输入关键词，程序会自动搜索相关图片\n"
            "2. 支持百度图片、必应图片等搜索引擎\n"
            "3. 多个关键词用逗号分隔，将依次搜索每个关键词\n"
            "4. 建议设置合理的延迟时间，避免被封IP"
        )
        info_label = ttk.Label(info_frame, text=info_text, wraplength=850)
        info_label.pack(fill=tk.X)
        row += 1
        
        ttk.Label(main_frame, text="搜索引擎:").grid(row=row, column=0, sticky=tk.W, pady=5)
        engine_frame = ttk.Frame(main_frame)
        engine_frame.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)
        
        self.engine_var = tk.StringVar(value='auto')
        engines = [
            ("自动检测", 'auto'),
            ("百度图片", 'baidu'),
            ("必应图片", 'bing'),
            ("通用网站", 'generic')
        ]
        
        for text, value in engines:
            ttk.Radiobutton(engine_frame, text=text, value=value, variable=self.engine_var).pack(side=tk.LEFT, padx=10)
        row += 1
        
        ttk.Label(main_frame, text="目标网站:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.url_entry = ttk.Entry(main_frame, width=60)
        self.url_entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
        self.url_entry.insert(0, "https://image.baidu.com")
        
        url_hint = ttk.Label(main_frame, text="(选择搜索引擎后，程序会自动构造搜索URL)", font=('Arial', 8))
        url_hint.grid(row=row+1, column=1, sticky=tk.W, padx=5)
        row += 2
        
        ttk.Label(main_frame, text="关键词 (逗号分隔):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.keywords_entry = ttk.Entry(main_frame, width=60)
        self.keywords_entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
        self.keywords_entry.insert(0, "风景,自然,高清")
        
        keyword_hint = ttk.Label(main_frame, text="例如: 白菜,汽车,猫咪  (必须填写关键词才能搜索相关图片)", font=('Arial', 8))
        keyword_hint.grid(row=row+1, column=1, sticky=tk.W, padx=5)
        row += 2
        
        ttk.Label(main_frame, text="图片数量:").grid(row=row, column=0, sticky=tk.W, pady=5)
        count_frame = ttk.Frame(main_frame)
        count_frame.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)
        self.count_var = tk.IntVar(value=20)
        self.count_spinbox = ttk.Spinbox(count_frame, from_=1, to=1000, textvariable=self.count_var, width=15)
        self.count_spinbox.pack(side=tk.LEFT)
        row += 1
        
        ttk.Label(main_frame, text="爬取页数:").grid(row=row, column=0, sticky=tk.W, pady=5)
        pages_frame = ttk.Frame(main_frame)
        pages_frame.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)
        self.pages_var = tk.IntVar(value=5)
        self.pages_spinbox = ttk.Spinbox(pages_frame, from_=1, to=50, textvariable=self.pages_var, width=15)
        self.pages_spinbox.pack(side=tk.LEFT)
        row += 1
        
        ttk.Label(main_frame, text="保存目录:").grid(row=row, column=0, sticky=tk.W, pady=5)
        save_frame = ttk.Frame(main_frame)
        save_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
        save_frame.columnconfigure(0, weight=1)
        self.save_dir_var = tk.StringVar(value=os.path.join(os.getcwd(), "downloads"))
        self.save_dir_entry = ttk.Entry(save_frame, textvariable=self.save_dir_var)
        self.save_dir_entry.grid(row=0, column=0, sticky=(tk.W, tk.E))
        self.browse_button = ttk.Button(save_frame, text="浏览", command=self._browse_save_dir)
        self.browse_button.grid(row=0, column=1, padx=5)
        row += 1
        
        ttk.Label(main_frame, text="请求延迟 (秒):").grid(row=row, column=0, sticky=tk.W, pady=5)
        delay_frame = ttk.Frame(main_frame)
        delay_frame.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)
        self.delay_var = tk.DoubleVar(value=1.5)
        self.delay_spinbox = ttk.Spinbox(delay_frame, from_=0.1, to=10.0, increment=0.1, textvariable=self.delay_var, width=15)
        self.delay_spinbox.pack(side=tk.LEFT)
        ttk.Label(delay_frame, text="(越小越快，但可能被封IP，建议1-2秒)").pack(side=tk.LEFT, padx=10)
        row += 1
        
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=2, pady=15)
        self.start_button = ttk.Button(button_frame, text="开始采集", command=self._start_crawl)
        self.start_button.pack(side=tk.LEFT, padx=10)
        self.stop_button = ttk.Button(button_frame, text="停止采集", command=self._stop_crawl, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=10)
        row += 1
        
        ttk.Label(main_frame, text="日志输出:").grid(row=row, column=0, sticky=tk.NW, pady=5)
        log_frame = ttk.Frame(main_frame)
        log_frame.grid(row=row, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5, padx=5)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=15)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.log_text.config(state=tk.DISABLED)
        row += 1
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100, mode='determinate')
        self.progress_bar.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        self.progress_label = ttk.Label(main_frame, text="进度: 0/0")
        self.progress_label.grid(row=row+1, column=0, columnspan=2, pady=5)
    
    def _browse_save_dir(self):
        directory = filedialog.askdirectory(initialdir=self.save_dir_var.get())
        if directory:
            self.save_dir_var.set(directory)
    
    def _log_message(self, message):
        self.root.after(0, self._append_log, message)
    
    def _append_log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def _update_progress(self):
        if self.crawler:
            current = self.crawler.downloaded_count
            total = self.crawler.max_images
            self.progress_label.config(text=f"进度: {current}/{total}")
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
        
        if not keywords:
            messagebox.showwarning("警告", "请输入关键词！\n例如: 白菜,汽车,猫咪\n关键词用于搜索相关图片。")
            return
        
        if not save_dir:
            messagebox.showerror("错误", "请选择保存目录")
            return
        
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.progress_var.set(0)
        
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        self.crawler = ImageCrawler(
            base_url=url,
            keywords=keywords,
            max_images=max_images,
            save_dir=save_dir,
            delay=delay,
            log_callback=self._log_message,
            search_engine=engine,
            max_pages=max_pages
        )
        
        def run_crawl():
            try:
                self.crawler.start()
            except Exception as e:
                    self._log_message(f"发生错误: {e}")
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
            messagebox.showinfo("完成", f"采集完成！共下载 {self.crawler.downloaded_count} 张图片")


def main():
    root = tk.Tk()
    app = ImageCrawlerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
