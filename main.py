import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import re
import time
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO


class ImageCrawler:
    def __init__(self, base_url, keywords, max_images, save_dir, 
                 user_agent=None, delay=1.0, log_callback=None):
        self.base_url = base_url
        self.keywords = [k.strip() for k in keywords.split(',') if k.strip()]
        self.max_images = max_images
        self.save_dir = save_dir
        self.downloaded_count = 0
        self.found_urls = set()
        self.is_running = True
        self.delay = delay
        
        self.headers = {
            'User-Agent': user_agent or (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': base_url
        }
        
        self.log_callback = log_callback

    def log(self, message):
        if self.log_callback:
            self.log_callback(message)

    def _make_request(self, url, timeout=15):
        try:
            time.sleep(self.delay)
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
        if ext not in valid_exts:
            return False
        
        return True

    def _extract_images_from_page(self, html, page_url):
        soup = BeautifulSoup(html, 'lxml')
        images = []
        
        for img_tag in soup.find_all('img'):
            if self.downloaded_count >= self.max_images:
                break
            
            src = img_tag.get('src', '')
            data_src = img_tag.get('data-src', '')
            data_lazy = img_tag.get('data-lazy', '')
            
            img_url = None
            
            if src and self._is_valid_image(src):
                img_url = src
            elif data_src and self._is_valid_image(data_src):
                img_url = data_src
            elif data_lazy and self._is_valid_image(data_lazy):
                img_url = data_lazy
            
            if img_url:
                img_url = urljoin(page_url, img_url)
                if img_url not in self.found_urls:
                    self.found_urls.add(img_url)
                    images.append(img_url)
        
        return images

    def _extract_links_from_page(self, html, page_url):
        soup = BeautifulSoup(html, 'lxml')
        links = []
        base_domain = urlparse(self.base_url).netloc
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            full_url = urljoin(page_url, href)
            parsed_url = urlparse(full_url)
            
            if parsed_url.netloc == base_domain:
                if full_url not in self.found_urls:
                    links.append(full_url)
        
        return links

    def _download_image(self, img_url):
        try:
            response = self._make_request(img_url)
            if not response:
                return False
            
            content_type = response.headers.get('Content-Type', '')
            if not content_type.startswith('image/'):
                return False
            
            img = Image.open(BytesIO(response.content))
            
            ext = img.format.lower() if img.format else 'jpg'
            filename = f"image_{self.downloaded_count + 1}.{ext}"
            filepath = os.path.join(self.save_dir, filename)
            
            img.save(filepath)
            self.downloaded_count += 1
            self.log(f"已下载: {filename} ({self.downloaded_count}/{self.max_images})")
            return True
            
        except Exception as e:
            self.log(f"下载图片失败 {img_url}: {e}")
            return False

    def start(self):
        self.log(f"开始爬取...")
        self.log(f"目标网站: {self.base_url}")
        self.log(f"关键词: {', '.join(self.keywords)}")
        self.log(f"最大图片数: {self.max_images}")
        self.log(f"保存目录: {self.save_dir}")
        
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir, exist_ok=True)
        
        pages_to_visit = [self.base_url]
        visited_pages = set()
        
        while self.is_running and self.downloaded_count < self.max_images:
            if not pages_to_visit:
                break
            
            current_page = pages_to_visit.pop(0)
            
            if current_page in visited_pages:
                continue
            
            visited_pages.add(current_page)
            
            self.log(f"正在访问页面: {current_page}")
            
            response = self._make_request(current_page)
            if not response:
                continue
            
            html = response.text
            
            img_urls = self._extract_images_from_page(html, current_page)
            self.log(f"在页面中找到 {len(img_urls)} 张图片")
            
            for img_url in img_urls:
                if not self.is_running:
                    break
                
                if self.downloaded_count >= self.max_images:
                    break
                
                self._download_image(img_url)
            
            if self.keywords:
                links = self._extract_links_from_page(html, current_page)
                for link in links:
                    if link not in pages_to_visit and link not in visited_pages:
                        for keyword in self.keywords:
                            if keyword.lower() in link.lower():
                                pages_to_visit.append(link)
                                break
        
        self.log(f"爬取完成! 共下载 {self.downloaded_count} 张图片")
        return self.downloaded_count

    def stop(self):
        self.is_running = False
        self.log("正在停止爬取...")


class ImageCrawlerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("图片采集工具")
        self.root.geometry("800x600")
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
        main_frame.rowconfigure(7, weight=1)
        
        row = 0
        
        ttk.Label(main_frame, text="目标网站:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.url_entry = ttk.Entry(main_frame, width=60)
        self.url_entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
        self.url_entry.insert(0, "https://www.baidu.com")
        row += 1
        
        ttk.Label(main_frame, text="关键词 (逗号分隔):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.keywords_entry = ttk.Entry(main_frame, width=60)
        self.keywords_entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
        row += 1
        
        ttk.Label(main_frame, text="图片数量:").grid(row=row, column=0, sticky=tk.W, pady=5)
        count_frame = ttk.Frame(main_frame)
        count_frame.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)
        self.count_var = tk.IntVar(value=10)
        self.count_spinbox = ttk.Spinbox(count_frame, from_=1, to=1000, textvariable=self.count_var, width=15)
        self.count_spinbox.pack(side=tk.LEFT)
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
        self.delay_var = tk.DoubleVar(value=1.0)
        self.delay_spinbox = ttk.Spinbox(delay_frame, from_=0.1, to=5.0, increment=0.1, textvariable=self.delay_var, width=15)
        self.delay_spinbox.pack(side=tk.LEFT)
        ttk.Label(delay_frame, text="(越小越快，但可能被封IP)").pack(side=tk.LEFT, padx=10)
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
        
        if not url:
            messagebox.showerror("错误", "请输入目标网站URL")
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
            log_callback=self._log_message
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
        messagebox.showinfo("完成", f"采集完成！共下载 {self.crawler.downloaded_count} 张图片")


def main():
    root = tk.Tk()
    app = ImageCrawlerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
