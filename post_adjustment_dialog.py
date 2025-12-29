#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SuperPicky V3.3 - Re-Star Dialog
重新评星对话框 - 完全重写版本
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, List, Set, Optional
from post_adjustment_engine import PostAdjustmentEngine, safe_int, safe_float
from exiftool_manager import get_exiftool_manager
from advanced_config import get_advanced_config
from i18n import get_i18n


class PostAdjustmentDialog:
    """重新评星对话框"""

    def __init__(self, parent, directory: str, current_sharpness: int = 500,
                 current_nima: float = 5.0, on_complete_callback=None):
        """
        初始化对话框

        Args:
            parent: 父窗口
            directory: 照片目录
            current_sharpness: 当前UI设置的锐度阈值
            current_nima: 当前UI设置的美学阈值
            on_complete_callback: 完成后的回调函数
        """
        self.window = tk.Toplevel(parent)

        # 初始化配置和国际化
        self.config = get_advanced_config()
        self.i18n = get_i18n(self.config.language)

        self.window.title(self.i18n.t("post_adjustment.title"))
        # V3.4: 优化窗口高度 - 默认紧凑，展开高级时动态扩展
        self.window.geometry("750x550")  # 默认紧凑高度
        self.window.resizable(True, True)  # 允许调整大小
        self.window.minsize(750, 520)  # 设置最小尺寸
        
        # 保存默认和扩展高度
        self.compact_height = 550
        self.expanded_height = 850
        
        # V3.3: 配置窗口样式，与主程序保持一致（不改变主题）
        self.window.configure(bg='#f0f0f0')  # 浅灰色背景
        
        # 配置 ttk 样式（只配置必要的颜色，不改变主题）
        style = ttk.Style()
        # 不调用 theme_use，保持与主窗口一致的主题
        
        # 只配置背景色
        style.configure('TFrame', background='#f0f0f0')
        style.configure('TLabelframe', background='#f0f0f0')
        style.configure('TLabelframe.Label', background='#f0f0f0', font=('PingFang SC', 14, 'bold'))

        self.directory = directory
        self.on_complete_callback = on_complete_callback

        # 初始化引擎
        self.engine = PostAdjustmentEngine(directory)

        # 0星阈值变量（从高级配置加载）
        self.min_confidence_var = tk.DoubleVar(value=self.config.min_confidence)
        self.min_sharpness_var = tk.IntVar(value=self.config.min_sharpness)
        self.min_nima_var = tk.DoubleVar(value=self.config.min_nima)

        # 2/3星阈值变量（从主界面当前设置加载）
        self.sharpness_threshold_var = tk.IntVar(value=current_sharpness)
        self.nima_threshold_var = tk.DoubleVar(value=current_nima)
        self.picked_percentage_var = tk.IntVar(value=self.config.picked_top_percentage)

        # 数据
        self.original_photos: List[Dict] = []
        self.updated_photos: List[Dict] = []
        self.picked_files: Set[str] = set()

        # 统计数据
        self.current_stats: Optional[Dict] = None
        self.preview_stats: Optional[Dict] = None

        # 防抖定时器
        self._preview_timer = None

        # 创建UI
        self._create_widgets()

        # 加载数据
        self._load_data()

        # 居中窗口
        self._center_window()

    def _create_widgets(self):
        """创建UI组件 - V3.4: 两列布局设计"""

        # ===== 顶部：两列布局 =====
        top_frame = ttk.Frame(self.window, padding=15)
        top_frame.pack(fill=tk.BOTH, expand=False, padx=15, pady=(15, 0))
        
        # 配置两列等宽
        top_frame.columnconfigure(0, weight=1)
        top_frame.columnconfigure(1, weight=1)

        # 左列：当前评星统计
        current_frame = ttk.LabelFrame(
            top_frame,
            text="  当前评星统计  ",
            padding=15
        )
        current_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 7))

        self.current_stats_label = tk.Text(
            current_frame,
            height=7,
            width=35,
            font=("PingFang SC", 13),
            spacing1=4,
            spacing2=2,
            spacing3=4,
            padx=10,  # 增加水平内边距
            pady=8,   # 增加垂直内边距
            relief=tk.FLAT,
            wrap=tk.WORD,
            bg='#fafafa',
            fg='#333',
            highlightthickness=0,
            borderwidth=0,
            state='disabled'
        )
        self.current_stats_label.pack(fill=tk.BOTH, expand=True)

        # 右列：调整后预览
        preview_frame = ttk.LabelFrame(
            top_frame,
            text="  调整后预览  ",
            padding=15
        )
        preview_frame.grid(row=0, column=1, sticky='nsew', padx=(7, 0))

        self.preview_stats_label = tk.Text(
            preview_frame,
            height=7,
            width=35,
            font=("PingFang SC", 13),
            spacing1=4,
            spacing2=2,
            spacing3=4,
            padx=10,  # 增加水平内边距
            pady=8,   # 增加垂直内边距
            relief=tk.FLAT,
            wrap=tk.WORD,
            bg='#fafafa',
            fg='#333',  # 改为默认深灰色，让红色tag能正常显示
            highlightthickness=0,
            borderwidth=0,
            state='disabled'
        )
        self.preview_stats_label.pack(fill=tk.BOTH, expand=True)

        # ===== 中间：阈值调整区域 =====
        threshold_frame = ttk.LabelFrame(
            self.window,
            text="  阈值调整（2/3星）  ",
            padding=15
        )
        threshold_frame.pack(fill=tk.X, padx=15, pady=(15, 10))

        # 锐度阈值
        self._create_slider(
            threshold_frame,
            "🔍 鸟锐度阈值 (2/3星):",
            self.sharpness_threshold_var,
            from_=300, to=1000,
            step=50,
            format_func=lambda v: f"{v:.0f}"
        )

        # 美学阈值
        self._create_slider(
            threshold_frame,
            "🎨 摄影美学阈值 (2/3星):",
            self.nima_threshold_var,
            from_=4.5, to=5.5,
            step=0.1,
            format_func=lambda v: f"{v:.1f}"
        )

        # 精选百分比
        self._create_slider(
            threshold_frame,
            "🏆 精选旗标百分比:",
            self.picked_percentage_var,
            from_=10, to=50,
            step=5,
            format_func=lambda v: f"{v:.0f}%"
        )

        # ===== 底部按钮（包含中间进度区域）=====
        btn_frame = ttk.Frame(self.window, padding=15)
        btn_frame.pack(fill=tk.X)
        
        # 左侧取消按钮
        ttk.Button(
            btn_frame,
            text="取消",
            command=self.window.destroy,
            width=15
        ).pack(side=tk.LEFT, padx=5)

        # 右侧应用按钮
        self.apply_btn = ttk.Button(
            btn_frame,
            text="✓ 应用新评星",
            command=self._apply_new_ratings,
            width=15,
            state='disabled'
        )
        self.apply_btn.pack(side=tk.RIGHT, padx=5)
        
        # 中间进度区域（初始隐藏，只在处理时显示）
        self.progress_frame = ttk.Frame(btn_frame)
        self.progress_label = ttk.Label(
            self.progress_frame,
            text="",
            font=("PingFang SC", 11),
            foreground="#333"
        )
        self.progress_label.pack()
        
        # ===== 高级设置（折叠，放在按钮之下）=====
        self.advanced_expanded = tk.BooleanVar(value=False)
        
        # 高级设置折叠按钮
        advanced_btn_frame = ttk.Frame(self.window)
        advanced_btn_frame.pack(fill=tk.X, padx=15, pady=(5, 0))
        
        self.advanced_btn = ttk.Checkbutton(
            advanced_btn_frame,
            text="▶ 高级: 0星筛选设置",
            variable=self.advanced_expanded,
            command=self._toggle_advanced,
            style='Toolbutton'
        )
        self.advanced_btn.pack(anchor=tk.W)

        # 高级设置内容区域
        self.advanced_frame = ttk.LabelFrame(
            self.window,
            text="  0星筛选阈值（技术质量不达标）  ",
            padding=15
        )
        # 默认不显示

        # 最低置信度
        self._create_slider(
            self.advanced_frame,
            "AI 最低置信度:",
            self.min_confidence_var,
            from_=0.3, to=0.8,
            step=0.05,
            format_func=lambda v: f"{v:.2f}"
        )

        # 最低锐度
        self._create_slider(
            self.advanced_frame,
            "头部最低锐度:",
            self.min_sharpness_var,
            from_=100, to=500,
            step=50,
            format_func=lambda v: f"{v:.0f}"
        )

        # 最低美学
        self._create_slider(
            self.advanced_frame,
            "最低美学评分:",
            self.min_nima_var,
            from_=3.0, to=5.0,
            step=0.1,
            format_func=lambda v: f"{v:.1f}"
        )

    def _toggle_advanced(self):
        """切换高级设置区域显示，并动态调整窗口高度"""
        if self.advanced_expanded.get():
            # 展开 - 增加窗口高度
            current_width = self.window.winfo_width()
            self.window.geometry(f"{current_width}x{self.expanded_height}")
            self.advanced_frame.pack(fill=tk.X, padx=15, pady=(5, 10))
            self.advanced_btn.config(text="▼ 高级: 0星筛选设置")
        else:
            # 折叠 - 恢复紧凑高度
            current_width = self.window.winfo_width()
            self.window.geometry(f"{current_width}x{self.compact_height}")
            self.advanced_frame.pack_forget()
            self.advanced_btn.config(text="▶ 高级: 0星筛选设置")

    def _create_slider(self, parent, label_text, variable, from_, to, step, format_func):
        """创建滑块组件，支持步进"""
        container = ttk.Frame(parent)
        container.pack(fill=tk.X, pady=6)

        # 标签（左侧）
        label = ttk.Label(
            container,
            text=label_text,
            width=18,
            font=("Arial", 13)
        )
        label.pack(side=tk.LEFT)

        # 滑块（中间）
        slider = ttk.Scale(
            container,
            from_=from_,
            to=to,
            variable=variable,
            orient=tk.HORIZONTAL,
            command=lambda v: self._on_slider_change(variable, float(v), step, value_label, format_func)
        )
        slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # 数值显示（右侧）
        value_label = ttk.Label(
            container,
            text=format_func(variable.get()),
            width=8,
            font=("Arial", 13)
        )
        value_label.pack(side=tk.LEFT)

        # 初始化标签
        self._snap_to_step(variable, variable.get(), step)
        value_label.config(text=format_func(variable.get()))

    def _snap_to_step(self, variable, value, step):
        """将值对齐到步进"""
        snapped = round(value / step) * step
        variable.set(snapped)

    def _on_slider_change(self, variable, value, step, value_label, format_func):
        """滑块变化回调：步进+更新标签+触发预览"""
        # 步进对齐
        self._snap_to_step(variable, value, step)

        # 更新数值标签
        value_label.config(text=format_func(variable.get()))

        # 触发预览更新
        self._on_threshold_changed()

    def _load_data(self):
        """加载CSV数据"""
        success, message = self.engine.load_report()

        if not success:
            messagebox.showerror(self.i18n.t("errors.error_title"), message)
            self.window.destroy()
            return

        self.original_photos = self.engine.photos_data.copy()

        # DEBUG: 打印加载的照片数量
        print(f"DEBUG: 加载了 {len(self.original_photos)} 张照片的数据")

        self.current_stats = self._get_original_statistics()

        # DEBUG: 打印统计结果
        print(f"DEBUG: 当前统计 = {self.current_stats}")

        self._update_current_stats_display()

        self.apply_btn.config(state='normal')
        # 初始化时触发预览计算，显示与当前相同的数据
        self._on_threshold_changed()


    def _get_original_statistics(self) -> Dict[str, int]:
        """获取原始统计（包括重新计算picked）"""
        stats = {
            'star_0': 0,
            'star_1': 0,
            'star_2': 0,
            'star_3': 0,
            'picked': 0,
            'total': len(self.original_photos)
        }

        star_3_photos = []

        for photo in self.original_photos:
            # 使用 safe_int 处理评分
            rating = safe_int(photo.get('rating', '0'), 0)

            if rating == 0:
                stats['star_0'] += 1
            elif rating == 1:
                stats['star_1'] += 1
            elif rating == 2:
                stats['star_2'] += 1
            elif rating == 3:
                stats['star_3'] += 1
                star_3_photos.append(photo)

        # 基于当前配置重新计算精选旗标数量
        picked_files = self.engine.recalculate_picked(
            star_3_photos,
            self.picked_percentage_var.get()
        )
        stats['picked'] = len(picked_files)

        return stats


    def _display_statistics(self):
        """显示统计信息（垂直多行格式）"""
        if not self.current_stats:
            return

        stats = self.current_stats
        total = stats['total']
        
        # 垂直格式显示，优化汉字和数字间距
        text = f"总共 {total} 张有鸟照片\n\n"
        text += f"⭐⭐⭐ 三星 ({stats['star_3']}) 张\n"
        text += f"  └─🏆 精选 ({stats['picked']}) 张\n"
        text += f"⭐⭐ 两星 ({stats['star_2']}) 张\n"
        text += f"⭐ 一星 ({stats['star_1']}) 张\n"
        text += f"0星 ({stats['star_0']}) 张"

        self.current_stats_label.config(state=tk.NORMAL)
        self.current_stats_label.delete("1.0", tk.END)
        self.current_stats_label.insert("1.0", text)
        self.current_stats_label.config(state=tk.DISABLED)

    def _update_current_stats_display(self):
        """更新当前统计显示"""
        self._display_statistics()

    def _on_threshold_changed(self):
        """阈值改变回调（防抖）"""
        if self._preview_timer:
            self.window.after_cancel(self._preview_timer)

        self._preview_timer = self.window.after(300, self._update_preview)

    def _update_preview(self):
        """更新预览统计"""
        # 获取当前阈值
        min_confidence = self.min_confidence_var.get()
        min_sharpness = self.min_sharpness_var.get()
        min_nima = self.min_nima_var.get()
        sharpness_threshold = self.sharpness_threshold_var.get()
        nima_threshold = self.nima_threshold_var.get()
        picked_percentage = self.picked_percentage_var.get()

        # 重新计算
        self.updated_photos = self.engine.recalculate_ratings(
            self.original_photos,
            min_confidence=min_confidence,
            min_sharpness=min_sharpness,
            min_nima=min_nima,
            sharpness_threshold=sharpness_threshold,
            nima_threshold=nima_threshold
        )

        star_3_photos = [p for p in self.updated_photos if p.get('新星级') == 3]
        self.picked_files = self.engine.recalculate_picked(star_3_photos, picked_percentage)

        self.preview_stats = self.engine.get_statistics(self.updated_photos)
        self.preview_stats['picked'] = len(self.picked_files)

        self._update_preview_display()

    def _update_preview_display(self):
        """更新预览显示（垂直多行格式，变化量红色高亮）"""
        if not self.preview_stats or not self.current_stats:
            return

        old = self.current_stats
        new = self.preview_stats
        total = new['total']
        
        # 检查是否有任何变化
        has_change = (
            new['star_3'] != old['star_3'] or
            new['star_2'] != old['star_2'] or
            new['star_1'] != old['star_1'] or
            new['star_0'] != old['star_0'] or
            new['picked'] != old.get('picked', 0)
        )
        
        # 启用编辑
        self.preview_stats_label.config(state=tk.NORMAL)
        self.preview_stats_label.delete("1.0", tk.END)
        
        # 配置红色tag用于高亮变化量
        self.preview_stats_label.tag_config("red", foreground="#d32f2f")
        
        # 总数
        self.preview_stats_label.insert("end", f"总共 {total} 张有鸟照片\n\n")
        
        # 三星 + 变化
        self.preview_stats_label.insert("end", f"⭐⭐⭐ 三星 ({new['star_3']}) 张")
        diff_3 = new['star_3'] - old['star_3']
        if diff_3 != 0:
            change_text = f" [{diff_3:+d}]"
            self.preview_stats_label.insert("end", change_text, "red")
        self.preview_stats_label.insert("end", "\n")
        
        # 精选 + 变化
        self.preview_stats_label.insert("end", f"  └─🏆 精选 ({new['picked']}) 张")
        diff_picked = new['picked'] - old.get('picked', 0)
        if diff_picked != 0:
            change_text = f" [{diff_picked:+d}]"
            self.preview_stats_label.insert("end", change_text, "red")
        self.preview_stats_label.insert("end", "\n")
        
        # 两星 + 变化
        self.preview_stats_label.insert("end", f"⭐⭐ 两星 ({new['star_2']}) 张")
        diff_2 = new['star_2'] - old['star_2']
        if diff_2 != 0:
            change_text = f" [{diff_2:+d}]"
            self.preview_stats_label.insert("end", change_text, "red")
        self.preview_stats_label.insert("end", "\n")
        
        # 一星 + 变化
        self.preview_stats_label.insert("end", f"⭐ 一星 ({new['star_1']}) 张")
        diff_1 = new['star_1'] - old['star_1']
        if diff_1 != 0:
            change_text = f" [{diff_1:+d}]"
            self.preview_stats_label.insert("end", change_text, "red")
        self.preview_stats_label.insert("end", "\n")
        
        # 0星 + 变化
        self.preview_stats_label.insert("end", f"0星 ({new['star_0']}) 张")
        diff_0 = new['star_0'] - old['star_0']
        if diff_0 != 0:
            change_text = f" [{diff_0:+d}]"
            self.preview_stats_label.insert("end", change_text, "red")
        # 禁止编辑
        self.preview_stats_label.config(state=tk.DISABLED)

    def _apply_new_ratings(self):
        """应用新评星（只处理评分有变化的照片）"""
        if not self.updated_photos:
            messagebox.showwarning(
                self.i18n.t("messages.hint"),
                self.i18n.t("post_adjustment.no_data_warning")
            )
            return

        # 过滤出评分有变化的照片
        changed_photos = []
        for photo in self.updated_photos:
            new_rating = photo.get('新星级', 0)
            old_rating = int(photo.get('rating', 0))
            if new_rating != old_rating:
                changed_photos.append(photo)
        
        if not changed_photos:
            messagebox.showinfo(
                self.i18n.t("messages.hint"),
                "当前阈值设置与原始评星一致，无需调整"
            )
            return

        # 确认对话框显示实际变化数量
        msg = f"将更新 {len(changed_photos)} 张照片的评星\n（共 {len(self.updated_photos)} 张有鸟照片）\n\n确定应用新评星？"

        if not messagebox.askyesno(self.i18n.t("post_adjustment.apply_confirm_title"), msg):
            return

        self.apply_btn.config(state='disabled')
        self.window.protocol("WM_DELETE_WINDOW", lambda: None)

        # 显示进度区域
        self.progress_frame.pack(fill=tk.X, padx=15, pady=10)
        self.progress_label.config(text="开始处理...")
        self.window.update()
        
        total_changed = len(changed_photos)
        batch_data = []
        not_found_count = 0

        # 准备数据阶段 - 数字进度显示
        for i, photo in enumerate(changed_photos):
            filename = photo['filename']
            file_path = self.engine.find_image_file(filename)

            if not file_path:
                not_found_count += 1
            else:
                rating = photo.get('新星级', 0)
                pick = 1 if filename in self.picked_files else 0
                batch_data.append({
                    'file': file_path,
                    'rating': rating,
                    'pick': pick
                })
            
            # 每10张更新一次进度显示
            if (i + 1) % 10 == 0 or i == total_changed - 1:
                self.progress_label.config(text=f"查找文件 {i+1}/{total_changed}")
                self.window.update()

        if not batch_data:
            self.progress_frame.pack_forget()
            self.apply_btn.config(state='normal')
            messagebox.showwarning(
                self.i18n.t("messages.hint"),
                f"未找到任何需要处理的文件（{not_found_count} 个文件不存在）"
            )
            return

        try:
            # EXIF写入阶段 - 分批处理，每批20个文件
            exiftool_mgr = get_exiftool_manager()
            total_files = len(batch_data)
            batch_size = 20
            
            success_count = 0
            failed_count = 0
            
            for i in range(0, total_files, batch_size):
                batch = batch_data[i:i+batch_size]
                current = min(i + batch_size, total_files)
                
                # 显示进度
                self.progress_label.config(text=f"写入EXIF {current}/{total_files}")
                self.window.update()
                
                # 处理这一批
                stats = exiftool_mgr.batch_set_metadata(batch)
                success_count += stats['success']
                failed_count += stats['failed']
            
            # CSV更新阶段
            self.progress_label.config(text="更新CSV报告...")
            self.window.update()

            csv_success, csv_msg = self.engine.update_report_csv(
                changed_photos,
                self.picked_files
            )
            
            if csv_success:
                print(f"✅ {csv_msg}")
            else:
                print(f"⚠️ {csv_msg}")

            self.progress_label.config(text="✅ 完成!")
            self.window.update()

            self.progress_frame.pack_forget()

            # 结果消息
            if not_found_count > 0:
                result_msg = f"✅ 成功: {success_count} 张\n❌ 失败: {failed_count} 张\n⏭️ 跳过(未找到): {not_found_count} 张"
            else:
                result_msg = f"✅ 成功: {success_count} 张\n❌ 失败: {failed_count} 张"

            messagebox.showinfo(self.i18n.t("post_adjustment.apply_success_title"), result_msg)

            if self.on_complete_callback:
                self.on_complete_callback()

            self.window.destroy()

        except Exception as e:
            self.progress_frame.pack_forget()
            self.apply_btn.config(state='normal')
            messagebox.showerror(
                self.i18n.t("post_adjustment.apply_error_title"),
                self.i18n.t("post_adjustment.apply_error_msg", error=str(e))
            )

    def _center_window(self):
        """居中窗口"""
        try:
            # 确保窗口已经完全创建
            self.window.update_idletasks()

            # 使用紧凑高度（不是硬编码的900）
            width = 750
            height = self.compact_height  # 使用动态高度

            # 计算居中位置
            screen_width = self.window.winfo_screenwidth()
            screen_height = self.window.winfo_screenheight()
            x = (screen_width // 2) - (width // 2)
            y = (screen_height // 2) - (height // 2)

            # 设置窗口位置
            self.window.geometry(f'{width}x{height}+{x}+{y}')
        except Exception as e:
            # 如果居中失败，不影响窗口显示
            print(f"警告: 窗口居中失败: {e}")
