# /// script
# dependencies = [
#   "async-tkinter-loop",
#   "google-generativeai",
#   "openai",
#   "pygments",
#   "tkinterweb",
#   "xmlformatter",
# ]
# ///

from dotenv import load_dotenv
load_dotenv(verbose=True, override=True)

from content_utils import fix_content
from prompt_stack_manager import PromptStackManager
try:
    from user_ui_model_local import UserUIModel
except:
    from user_ui_model import UserUIModel

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from tkinter import StringVar

USE_PYGMENTS = True
if USE_PYGMENTS:
    import re
    import pygments
    from pygments import lexers
    from pygments.formatters import HtmlFormatter
    import tkinterweb  # For HTML rendering

import asyncio
from queue import Queue
from async_tkinter_loop import async_handler, async_mainloop

import ast
import json
import time
import uuid

import pathlib
import threading

# https://stackoverflow.com/a/77322684
import base64
class BytesEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, bytes):
            return base64.b64encode(o).decode("ascii")
        else:
            return super().default(o)

class LLMControlUI:
    def __init__(self, root, queue):
        self.queue = queue
        self.root = root
        self.root.title("LLM Interface")
        self.root.geometry("1280x800")

        self.ui_model = UserUIModel()
        self.prompt_manager = PromptStackManager()

        self.seq_user = 0
        self.seq_model = 0
        self.history = []
        self.stopped = False

        # ZMQ connection
        self.zmq_context = None
        self.zmq_publisher = None
        self.zmq_subscriber = None
        self.zmq_own_id = str(uuid.uuid4())

        try:
            import zmq

            self.zmq_context = zmq.Context()
            self.zmq_publisher = self.zmq_context.socket(zmq.PUB)
            self.zmq_publisher.connect("tcp://localhost:5560")
            self.zmq_subscriber = self.zmq_context.socket(zmq.SUB)
            self.zmq_subscriber.connect("tcp://localhost:5559")
            self.zmq_subscriber.setsockopt_string(zmq.SUBSCRIBE, "")
        except:
            pass

        # Create main frame
        main_frame = ttk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create paned window
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)

        # Create left frame for tree view
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        paned_window.add(left_frame)

        # Create search frame
        search_frame = ttk.Frame(left_frame)
        search_frame.pack(fill=tk.X, pady=(0, 10))

        # Create search entry
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Create search button
        self.search_button = ttk.Button(search_frame, text="Search", command=self.perform_search)
        self.search_button.pack(side=tk.LEFT, padx=(5, 0))

        # Create clear search button
        self.clear_search_button = ttk.Button(search_frame, text="Clear", command=self.clear_search)
        self.clear_search_button.pack(side=tk.LEFT, padx=(5, 0))

        # Create tree view
        self.tree = ttk.Treeview(left_frame, columns=("Role", "Sequence", "Size", "Content"), show="headings")
        self.tree.heading("Role", text="Role")
        self.tree.heading("Sequence", text="Seq.")
        self.tree.heading("Size", text="Size")
        self.tree.heading("Content", text="Content")
        self.tree.column("Role", minwidth=50, width=50, stretch=False)
        self.tree.column("Sequence", minwidth=50, width=50, stretch=False)
        self.tree.column("Size", minwidth=50, width=50, stretch=False)
        self.tree.column("Content", stretch=True)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Add scrollbar to tree view
        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scrollbar.set)

        # Bind selection event to update preview
        self.tree.bind("<<TreeviewSelect>>", self.update_preview)

        # Bind double-click event
        self.tree.bind("<Double-1>", self.edit_item)

        # Create right-click menu
        self.context_menu = tk.Menu(self.tree, tearoff=0)
        self.context_menu.add_command(label="Edit", command=self.edit_item)
        self.context_menu.add_command(label="Delete", command=self.delete_item)
        self.tree.bind("<Button-3>", self.show_context_menu)

        # Create input frame
        input_frame = ttk.Frame(root)
        input_frame.pack(fill=tk.X, padx=10, pady=10)

        # Create prompt selector frame
        self.prompt_frame = ttk.Frame(input_frame)
        self.prompt_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 5))

        # Create input box (now scrolledtext)
        self.input_box = scrolledtext.ScrolledText(input_frame, height=5)
        self.input_box.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Create file picker button
        self.file_picker_button = ttk.Button(input_frame, text="...", width=3, command=self.toggle_file_picker)
        self.file_picker_button.pack(side=tk.LEFT, padx=(5, 0))
        self.selected_file_path = None

        # Create button frame
        button_frame = ttk.Frame(input_frame)
        button_frame.pack(side=tk.RIGHT)

        # Create send button
        send_button = ttk.Button(button_frame, text="Send", command=async_handler(self.send_message))
        send_button.pack(side=tk.TOP, pady=2)

        # Add broadcast button
        self.broadcast_button = ttk.Button(button_frame, text="Broadcast", command=self.broadcast_message)
        self.broadcast_button.pack(side=tk.TOP, pady=2)

        # Add queue-to-local button
        self.queue_to_local_button = ttk.Button(button_frame, text="Q to Local", command=self.queue_to_local)
        self.queue_to_local_button.pack(side=tk.TOP, pady=2)

        # Add queue text box
        self.queue_text = scrolledtext.ScrolledText(root, height=1, wrap=tk.WORD)
        self.queue_text.pack(side=tk.LEFT, fill=tk.X, padx=10, expand=True)

        # Create right frame for preview
        self.right_frame = ttk.Frame(main_frame)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        paned_window.add(self.right_frame)

        # Viewer selection frame
        viewer_frame = ttk.Frame(self.right_frame)
        viewer_frame.pack(fill=tk.X, padx=2, pady=5)
        
        # Radio buttons to select viewer type
        self.viewer_type = tk.StringVar(value="text")
        ttk.Radiobutton(viewer_frame, text="Plain Text", variable=self.viewer_type, value="text", command=self.update_viewer).pack(side=tk.LEFT)
        ttk.Radiobutton(viewer_frame, text="Syntax Highlight", variable=self.viewer_type, value="html", command=self.update_viewer).pack(side=tk.LEFT)

        # Content formatting options
        self.formatting_clean_xml = tk.BooleanVar(value=False)
        ttk.Checkbutton(viewer_frame, text="Clean XML", variable=self.formatting_clean_xml, command=self.update_preview).pack(side=tk.LEFT, padx=(0, 10))

        # Font size selector
        ttk.Label(viewer_frame, text="").pack(side=tk.LEFT, expand=True)
        ttk.Label(viewer_frame, text="Font Size (px):").pack(side=tk.LEFT, padx=5)
        self.font_size = 12
        self.font_size_var = tk.StringVar(value="12")
        self.font_size_spinbox = ttk.Spinbox(viewer_frame, from_=8, to=32, textvariable=self.font_size_var, width=5, command=self.update_font_size)
        self.font_size_spinbox.pack(side=tk.LEFT)
        self.font_size_var.trace("w", lambda *args: self.update_font_size())

        # Add horizontal separator
        self.content_separator = ttk.Separator(self.right_frame, orient=tk.HORIZONTAL)
        self.content_separator.pack(fill=tk.X, pady=(5, 5))

        # Create content frame to hold the preview
        self.content_frame = ttk.Frame(self.right_frame, style='ContentFrame.TFrame')
        self.content_frame.pack(fill=tk.BOTH, expand=True)

        # Initialize viewer
        self.preview_text = None
        self.update_viewer()

        # Start ZMQ subscriber thread
        if self.zmq_subscriber:
            self.zmq_thread = threading.Thread(target=self.zmq_subscriber_loop, daemon=True)
            self.zmq_thread.start()

        # Create menu bar
        menubar = tk.Menu(root)
        root.config(menu=menubar)

        # Create file menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Load Context", command=self.load_context)
        file_menu.add_command(label="Save Context", command=self.save_context)

        # Create Model menu
        self.model_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Model", menu=self.model_menu)
        self._create_model_menu()

        # Create Settings menu
        self.settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=self.settings_menu)
        self._update_settings_menu()

        # Create Prompt Stack menu
        self.prompt_stack_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Prompt Stack", menu=self.prompt_stack_menu)
        self._create_prompt_stack_menu()

        # Create status bar
        self.status_bar = ttk.Frame(root)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

        # LLM response latency
        self.latency_var = StringVar(value="Latency: N/A")
        ttk.Label(self.status_bar, textvariable=self.latency_var).pack(side=tk.LEFT, padx=(0, 10))

        # LLM current status
        self.status_var = StringVar(value="Status: IDLE")
        ttk.Label(self.status_bar, textvariable=self.status_var).pack(side=tk.LEFT, padx=(0, 10))

        # Token count
        self.token_count_var = StringVar(value="Tokens: 0")
        ttk.Label(self.status_bar, textvariable=self.token_count_var).pack(side=tk.LEFT)

        # Search results count
        self.search_results_var = StringVar(value="Search Results: 0")
        ttk.Label(self.status_bar, textvariable=self.search_results_var).pack(side=tk.RIGHT)

        # Close handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # FIXME: Throw dialog for unsaved changes
    def on_close(self):
        self.stopped = True
        self.root.destroy()
        self.root.quit()
        exit(0)

    def perform_search(self):
        search_term = self.search_var.get().lower()
        if not search_term:
            return

        matches = 0
        for item in self.tree.get_children():
            index = self.tree.index(item)
            content = self.history[index]["parts"][0]

            if search_term in content.lower():
                self.tree.item(item, tags=('match',))
                matches += 1
            else:
                self.tree.item(item, tags=())

        self.tree.tag_configure('match', background='yellow')
        self.search_results_var.set(f"Search Results: {matches}")

    def toggle_file_picker(self):
        if self.selected_file_path:
            self.clear_selected_file()
        else:
            self.open_file_picker()

    def open_file_picker(self):
        file_path = filedialog.askopenfilename()
        if file_path:
            self.selected_file_path = file_path
            self.file_picker_button.config(text="CL")

    def clear_selected_file(self):
        self.selected_file_path = None
        self.file_picker_button.config(text="...")

    def clear_search(self):
        self.search_var.set("")
        for item in self.tree.get_children():
            self.tree.item(item, tags=())
        self.search_results_var.set("Search Results: 0")

    def update_viewer(self):
        """Switches between plain text and syntax-highlighted viewers."""
        if self.preview_text:
            self.preview_text.pack_forget()
            self.preview_text.destroy()
            self.preview_text = None
        
        if self.viewer_type.get() == "text":
            self.preview_text = scrolledtext.ScrolledText(self.content_frame, wrap=tk.WORD, width=50)
        else:
            self.create_syntax_highlighted_display()
        
        self.preview_text.pack(fill=tk.BOTH, expand=True)
        self.update_preview()
    
    def update_font_size(self, event=None):
        """Updates the font size in the syntax-highlighted viewer."""
        try:
            self.font_size = int(self.font_size_var.get())
            self.update_preview()
        except ValueError:
            messagebox.showerror("Error", "Font size must be an integer.")

    def create_syntax_highlighted_display(self):
        """Replace the preview text widget with a syntax-highlighting capable one"""
        # Create new display using tkinterweb
        self.preview_text = tkinterweb.HtmlFrame(self.content_frame, messages_enabled=False, horizontal_scrollbar="auto")
        # Do not use threading
        self.preview_text.html.max_thread_count = 0

        # Configure HTML/CSS for syntax highlighting
        self.html_formatter = HtmlFormatter(style='monokai', lineseparator='<br/>')
        self.css = self.html_formatter.get_style_defs('.highlight')

    def update_preview(self, event=None):
        selected_items = self.tree.selection()
        if selected_items:
            item = selected_items[0]
            item_id = self.tree.index(item)
            sequence = self.history[item_id].get("sequence", "N/A")
            role = self.history[item_id]["role"]

            # Get content
            content = self.history[item_id]["parts"][0]

            # Apply any rendering fix-ups
            content = fix_content(content, self.formatting_clean_xml.get())

            # Non-HTML
            if self.viewer_type.get() == "text":
                self.preview_text.delete("1.0", tk.END)
                self.preview_text.insert(tk.END, content)
                return

            # Process content to handle markdown with code blocks
            processed_content = ""
            
            # Default to markdown for most content
            default_lexer = lexers.get_lexer_by_name("markdown")
            
            # Regular expression to find code blocks ```language ... ```
            code_blocks = re.finditer(r'(```(\w*)\n)(.*?)(\n```)', content, re.DOTALL)
            
            last_end = 0
            has_code_blocks = False
            
            for match in code_blocks:
                has_code_blocks = True
                start, end = match.span()
                
                # Add text before this code block using markdown lexer
                if start > last_end:
                    markdown_part = content[last_end:start]
                    processed_content += pygments.highlight(markdown_part, default_lexer, self.html_formatter)
                
                # Extract opening, language, code and closing parts
                opening = match.group(1)  # ```language\n
                lang = match.group(2).strip() or None
                code = match.group(3)
                closing = match.group(4)  # \n```
                
                # First highlight the opening backticks with markdown lexer
                processed_content += pygments.highlight(opening, default_lexer, self.html_formatter)
                
                try:
                    # Try to use the specified language
                    if lang and lang.lower() not in ('text', 'plain', 'markdown', 'md'):
                        code_lexer = lexers.get_lexer_by_name(lang.lower())
                    else:
                        # Try to guess if no useful language is specified
                        code_lexer = lexers.guess_lexer(code)
                except:
                    # Default to text if we can't determine the language
                    code_lexer = lexers.get_lexer_by_name("text")
                    
                # Highlight the code block with appropriate lexer
                highlighted_code_part = pygments.highlight(code, code_lexer, self.html_formatter)
                processed_content += highlighted_code_part
                
                # Highlight the closing backticks with markdown lexer
                processed_content += pygments.highlight(closing, default_lexer, self.html_formatter)
                
                last_end = end
                
            # Add any remaining text after the last code block
            if last_end < len(content):
                remaining = content[last_end:]
                processed_content += pygments.highlight(remaining, default_lexer, self.html_formatter)
                
            # If no code blocks were found, just use markdown for everything
            if not has_code_blocks:
                processed_content = pygments.highlight(content, default_lexer, self.html_formatter)
                
            # Store the processed content for the next steps    
            highlighted_code = processed_content
           
            # TASK: Process the highlighted code to preserve whitespace while allowing wrapping
            #
            # First, convert spaces to non-breaking spaces to preserve consecutive spaces
            # and replace tabs with the appropriate number of spaces
            def process_content(match):
                span_tag = match.group(1)  # This is the full span tag with attributes
                content = match.group(2)   # This is just the content inside the span
                
                # Replace leading spaces with non-breaking spaces
                processed = re.sub(r'^([ \t]+)', lambda m: '&nbsp;' * len(m.group(1)), content, flags=re.MULTILINE)
                # Replace consecutive spaces with alternating space and non-breaking space
                processed = re.sub(r'  +', lambda m: '&nbsp; ' * (len(m.group(0)) // 2) + ('&nbsp;' if len(m.group(0)) % 2 else ''), processed)
                
                # Return the span with its original attributes but processed content
                return f'<span {span_tag}>{processed}</span>'
                
            # Use a regex to capture the content between span tags and process it
            # The regex now captures both the span attributes and the content separately
            highlighted_code = re.sub(r'<span([^>]*)>(.*?)</span>', process_content, highlighted_code, flags=re.DOTALL)
            
            # Then replace the pre tag with our wrapper div
            highlighted_code = highlighted_code.replace(
                '<div class="highlight"><pre>', 
                '<div class="highlight"><div class="code-wrapper">'
            ).replace('</pre></div>', '</div></div>')

            # Create complete HTML document
            css = self.css + f"""
                body {{ 
                    font-size: {self.font_size}px; 
                }}
            """
            
            html_content = f"""
            <html>
            <head>
                <style>
                    body {{ 
                        background-color: #282828;
                        color: #f8f8f2;
                        font-family: 'IBM Plex Mono', 'Consolas', 'Monaco', monospace;
                        padding: 2px;
                    }}
                    .metadata {{
                        color: #66d9ef;
                        margin-bottom: 10px;
                    }}
                    .code-wrapper {{
                        font-family: monospace;
                        margin: 0;
                        padding: 0;
                    }}
                    {css}
                </style>
            </head>
            <body>
                <div class="metadata">
                    Sequence: {sequence}<br>
                    Role: {role}
                </div>
                {highlighted_code}
            </body>
            </html>
            """
            
            # Update the display
            self.preview_text.load_html(html_content)

    def _update_prompt_selector_ui(self):
        """Update the prompt selector buttons"""
        # Clear existing buttons
        for widget in self.prompt_frame.winfo_children():
            widget.destroy()

        prompts = self.prompt_manager.prompts
        if not prompts:
            # Show "No prompts" label if no prompts available
            ttk.Label(self.prompt_frame, text="No prompts available").pack(side=tk.LEFT)
            return

        # Create a button for each prompt
        for i, prompt in enumerate(prompts):
            filename = self.prompt_manager.get_prompt_filename(i)
            btn = ttk.Button(
                self.prompt_frame,
                text=filename,  # Show filename instead of number
                command=lambda idx=i: self._select_prompt(idx)
            )
            btn.pack(side=tk.LEFT, padx=(0, 2))

            # Add tooltip with prompt preview
            self._create_tooltip(btn, prompt[:100] + ("..." if len(prompt) > 100 else ""))

    def _create_tooltip(self, widget, text):
        """Create a tooltip for a widget"""
        def enter(event):
            x, y, _, _ = widget.bbox("insert")
            x += widget.winfo_rootx() + 25
            y += widget.winfo_rooty() + 20

            # Create tooltip window
            self.tooltip = tk.Toplevel(widget)
            self.tooltip.wm_overrideredirect(True)
            self.tooltip.wm_geometry(f"+{x}+{y}")

            label = ttk.Label(self.tooltip, text=text, justify=tk.LEFT,
                            background="#ffffe0", relief="solid", borderwidth=1)
            label.pack()

        def leave(event):
            if hasattr(self, 'tooltip'):
                self.tooltip.destroy()
                del self.tooltip

        widget.bind('<Enter>', enter)
        widget.bind('<Leave>', leave)

    def _select_prompt(self, index: int):
        """Handle prompt selection"""
        self.prompt_manager.set_current_prompt(index)

        # Update button styles to show selection
        for i, btn in enumerate(self.prompt_frame.winfo_children()):
            if i == index:
                btn.state(['pressed'])  # Highlight selected button
            else:
                btn.state(['!pressed'])  # Un-highlight other buttons

    def _on_prompt_selected(self, event):
        """Handle prompt selection"""
        if self.prompt_selector.get() != "No prompts available":
            # Extract index from the selection (assumes "N. prompt..." format)
            index = int(self.prompt_selector.get().split('.')[0]) - 1
            self.prompt_manager.set_current_prompt(index)

    def _on_stack_selected(self, *args):
        """Handle stack selection"""
        if not self.selected_stack.get():
            return
        try:
            self.prompt_manager.load_stack(self.selected_stack.get())
            self._update_prompt_selector_ui()
            # Select first prompt by default
            if self.prompt_manager.prompts:
                self._select_prompt(0)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load prompt stack: {str(e)}")

    def _create_prompt_stack_menu(self):
        """Create simple stack selection menu"""
        self.prompt_stack_menu.delete(0, tk.END)

        if not hasattr(self, 'selected_stack'):
            self.selected_stack = tk.StringVar()
            self.selected_stack.trace("w", self._on_stack_selected)

        stacks = self.prompt_manager.get_available_stacks()
        if not stacks:
            self.prompt_stack_menu.add_command(
                label="No stacks found",
                state="disabled"
            )
        else:
            for stack in sorted(stacks):
                self.prompt_stack_menu.add_radiobutton(
                    label=stack,
                    variable=self.selected_stack,
                    value=stack
                )

    def _on_model_changed(self, *args):
        """Handle model selection changes"""
        if not self.selected_model.get():
            return
            
        provider_name, model_id = self.selected_model.get().split(":")
        self.ui_model.set_provider(provider_name)
        self.ui_model.set_model(model_id)
        
        # Update provider settings menu
        self._update_provider_settings()

    def _create_model_menu(self):
        """Create the model selection dropdown"""
        # Initialize selected model if not exists
        if not hasattr(self, 'selected_model'):
            self.selected_model = tk.StringVar()
            if self.ui_model.current_provider and self.ui_model.current_model:
                current = f"{self.ui_model.current_provider.name}:{self.ui_model.current_model}"
                self.selected_model.set(current)

        def update_model(*args):
            if not self.selected_model.get():
                return
            provider_name, model_id = self.selected_model.get().split(":")
            self.ui_model.set_provider(provider_name)
            self.ui_model.set_model(model_id)
            self._update_settings_menu()

        self.selected_model.trace("w", update_model)
       
        # Add all models in a flat list
        for provider_name, provider in self.ui_model.get_providers().items():
            for model in provider.get_available_models():
                model_value = f"{provider_name}:{model.id}"
                label = f"{model.name} ({provider_name})"
                self.model_menu.add_radiobutton(
                    label=label,
                    variable=self.selected_model,
                    value=model_value
                )

    def _update_settings_menu(self):
        """Update settings menu based on current provider"""
        # Clear existing settings
        self.settings_menu.delete(0, tk.END)
        
        current_provider = self.ui_model.current_provider
        if not current_provider:
            return
            
        # Add provider name as header (disabled menu item)
        self.settings_menu.add_command(
            label=f"Provider: {current_provider.name}",
            state="disabled"
        )
        self.settings_menu.add_separator()
        
        settings = current_provider.get_settings()
        
        for key, knob in settings.items():
            ui_component = knob.get_ui_component()
            if ui_component["type"] == "slider":
                self._create_slider_menu_item(key, ui_component)
            elif ui_component["type"] == "dropdown":
                self._create_dropdown_menu_item(key, ui_component)
            elif ui_component["type"] == "checkbox":
                self._create_checkbox_menu_item(key, ui_component)

    def _create_slider_menu_item(self, key, ui_component):
        def format_value(value, is_integer):
            return f"{int(value)}" if is_integer else f"{value:.2f}"

        def update_value(value):
            if ui_component["is_integer"]:
                float_value = int(float(value))
            else:
                float_value = float(value)
            self.ui_model.get_knobs()[key].set_value(float_value)
            current_value_label.config(text=f"Current: {format_value(float_value, ui_component['is_integer'])}")

        slider_window = tk.Toplevel(self.root)
        slider_window.title(ui_component["name"])
        slider_window.withdraw()
        slider_window.protocol("WM_DELETE_WINDOW", slider_window.withdraw)

        # Main frame
        main_frame = ttk.Frame(slider_window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Parameter label
        ttk.Label(main_frame, text=f"Adjusting: {ui_component['name']}", font=("", 12, "bold")).pack(pady=(0, 10))

        # Slider frame
        slider_frame = ttk.Frame(main_frame)
        slider_frame.pack(fill=tk.X, expand=True)

        # Min label
        ttk.Label(slider_frame, text=f"Min: {format_value(ui_component['min'], ui_component['is_integer'])}").pack(side=tk.LEFT)

        # Slider
        slider = ttk.Scale(slider_frame, from_=ui_component["min"], to=ui_component["max"],
                           value=ui_component["value"], command=update_value)
        slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        # Max label
        ttk.Label(slider_frame, text=f"Max: {format_value(ui_component['max'], ui_component['is_integer'])}").pack(side=tk.LEFT)

        # Current value label
        current_value_label = ttk.Label(main_frame, text=f"Current: {format_value(ui_component['value'], ui_component['is_integer'])}")
        current_value_label.pack(pady=(10, 0))

        self.settings_menu.add_command(label=ui_component["name"],
                                       command=lambda: slider_window.deiconify())

    def _create_dropdown_menu_item(self, key, ui_component):
        value = tk.StringVar(value=ui_component["value"])

        def update_value(*args):
            self.ui_model.get_knobs()[key].set_value(value.get())

        value.trace("w", update_value)

        dropdown_menu = tk.Menu(self.settings_menu, tearoff=0)
        for option in ui_component["options"]:
            dropdown_menu.add_radiobutton(label=option, variable=value, value=option)

        self.settings_menu.add_cascade(label=ui_component["name"], menu=dropdown_menu)

    def _create_checkbox_menu_item(self, key, ui_component):
        value = tk.BooleanVar(value=ui_component["value"])

        def update_value():
            self.ui_model.get_knobs()[key].set_value(value.get())

        self.settings_menu.add_checkbutton(label=ui_component["name"],
                                           variable=value, command=update_value)

    def show_context_menu(self, event):
        selected_items = self.tree.selection()
        if selected_items:
            self.context_menu.post(event.x_root, event.y_root)

    def delete_item(self):
        selected_items = self.tree.selection()
        for item in reversed(selected_items):  # Reverse to maintain correct indices
            index = self.tree.index(item)
            self.tree.delete(item)
            del self.history[index]

    def edit_item(self, event=None):
        item = self.tree.selection()[0]
        index = self.tree.index(item)
        role = self.history[index]["role"]
        content = self.history[index]["parts"][0]
        sequence = self.history[index].get("sequence")

        # Create pop-up dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit Content")
        dialog.geometry("800x600")

        # Create and pack a ScrolledText widget
        text_widget = scrolledtext.ScrolledText(dialog)
        text_widget.pack(expand=True, fill='both', padx=10, pady=10)
        text_widget.insert(tk.END, content)

        def save_changes():
            new_content = text_widget.get("1.0", tk.END).strip()
            self.history[index]["parts"][0] = new_content
            new_content_size = len(new_content)
            self.tree.item(item, values=(role, sequence, new_content_size, new_content))
            dialog.destroy()

        # Create button frame
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)

        # Create OK and Cancel buttons
        ok_button = ttk.Button(button_frame, text="OK", command=save_changes)
        ok_button.pack(side=tk.LEFT, padx=5)
        cancel_button = ttk.Button(button_frame, text="Cancel", command=dialog.destroy)
        cancel_button.pack(side=tk.LEFT, padx=5)

    def queue_to_local(self):
        queue_content = self.queue_text.get("1.0", tk.END).strip()
        if queue_content:
            self.input_box.insert(tk.END, queue_content + "\n")
        self.queue_text.delete("1.0", tk.END)

    def broadcast_message(self):
        message = self.queue_text.get("1.0", tk.END).strip()
        if message:
            message = {'zmq_id': self.zmq_own_id, 'text': message}
            if self.zmq_publisher:
                self.zmq_publisher.send_pyobj(message)

    def zmq_subscriber_loop(self):
        import zmq
        while True:
            try:
                message = self.zmq_subscriber.recv_pyobj()
                if message['zmq_id'] != self.zmq_own_id:
                    self.update_queue_text(message['text'])
            except zmq.ZMQError:
                break

    def update_queue_text(self, message):
        def tk_command():
            self.queue_text.insert(tk.END, f"Received: {message}\n")
            self.queue_text.see(tk.END)
        self.add_task_to_queue(tk_command)

    async def send_message(self):
        message = self.input_box.get("1.0", tk.END).strip()
        if message:
            # Update sequence counter
            self.seq_user += 1
            my_seq = self.seq_user

            # Add file data
            # FIXME: Extend beyond .mp3
            parts = [message]
            if self.selected_file_path:
                if self.selected_file_path.endswith(".mp3"):
                    parts.append({
                        "mime_type": "audio/mp3",
                        "data": pathlib.Path(self.selected_file_path).read_bytes()
                    })
                    print(">> File loaded:", self.selected_file_path)
                    self.selected_file_path = None

            displayed_message = self.format_content_for_display(message)
            displayed_message_size = len(displayed_message)
            self.tree.insert("", tk.END, values=("user", my_seq, displayed_message_size, displayed_message))
            self.input_box.delete("1.0", tk.END)

            # Update status
            self.status_var.set("Status: RUNNING")
            self.root.update()

            # Get LLM response
            self.chat_session = self.ui_model.generate_chat_session(self.history, self.prompt_manager.get_current_prompt())
            self.history.append({"role": "user", "parts": parts, "sequence": my_seq})

            start_time = time.time()
            try:
                r = await self.chat_session.send_message_async(message)
            except:
                print(f"FAIL, message sent to LLM: {message}")
                self.status_var.set("Status: FAIL")
                self.latency_var.set("Latency: N/A")
                self.token_count_var.set("Tokens: N/A")
                raise

            # Calculate latency
            latency = time.time() - start_time
            self.latency_var.set(f"Latency: {latency:.2f}s")

            # Fix-up
            r_text = r.text
            r_text = r_text.strip()

            # Metadata
            # -- print(r.usage_metadata)
            token_count = r.usage_metadata.total_token_count
            self.token_count_var.set(f"Tokens: {token_count}")

            self.history.append({"role": "model", "parts": [r_text], "sequence": my_seq})
            displayed_response = self.format_content_for_display(r_text)
            displayed_response_size = len(displayed_response)
            self.tree.insert("", tk.END, values=("model", my_seq, displayed_response_size, displayed_response))

            # Update status to IDLE
            self.status_var.set("Status: IDLE")
            self.root.update()

    def scroll_tree_to_bottom(self):
        children = self.tree.get_children()
        if children:
            last_item = children[-1]
            self.tree.see(last_item)
            self.tree.selection_set(last_item)

    def load_context(self):
        file_path = filedialog.askopenfilename(filetypes=[("Python files", "*.py"), ["Text files", "*.txt"]])
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    content = file.read()

                    # Reset sequence counters
                    self.seq_user = 0
                    self.seq_model = 0

                    # Check if the file starts with the specific comment
                    if content.strip().startswith('"""'):
                        # Find the start of the history
                        history_start = content.find("history=")
                        if history_start == -1:
                            raise ValueError("Could not find 'history=' in the file")
                        content = content[history_start:]

                        # Remove the trailing code if present
                        trailing_code = ')\n\nresponse = chat_session.send_message("INSERT_INPUT_HERE")\n\nprint(response.text)'
                        content = content.removesuffix(trailing_code)

                    # Extract the history list from the file content
                    history_str = content.split("history=")[1].strip()
                    self.history = ast.literal_eval(history_str)

                    # No sequence numbers at all?
                    assign_sequences = False
                    if all("sequence" not in item for item in self.history):
                        assign_sequences = True

                    # Assign or update sequence numbers
                    for item in self.history:
                        if assign_sequences and not item.get("sequence"):
                            if item["role"] == "user":
                                self.seq_user += 1
                                item["sequence"] = self.seq_user
                            elif item["role"] == "model":
                                self.seq_model += 1
                                item["sequence"] = self.seq_model
                        else:
                            # Update counters based on existing sequence numbers
                            seq = item.get("sequence")
                            if seq:
                                if item["role"] == "user":
                                    self.seq_user = max(self.seq_user, seq)
                                elif item["role"] == "model":
                                    self.seq_model = max(self.seq_model, seq)

                    def load_bytes(input: dict):
                        if "mime_type" in input and "data" in input:
                            data_bytes = base64.b64decode(input["data"])
                            input["data"] = data_bytes
                            print(f">> Loaded data: {len(data_bytes)} bytes")
                        else:
                            print(">> Warning: Skipped input dict!")
                        return input

                    # Strip things to economize on tokens
                    for item in self.history:
                        parts = []
                        for part in item["parts"]:
                            if item["role"] == "user":
                                if isinstance(part, str):
                                    parts.append(part.strip())
                                else:
                                    parts.append(load_bytes(part))
                            else:
                                if isinstance(part, str):
                                    parts.append(part.strip())
                                else:
                                    parts.append(load_bytes(part))
                        item["parts"] = parts

                    self.update_tree_view()
                    self.scroll_tree_to_bottom()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load context: {str(e)}")
                raise

    def save_context(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".py", filetypes=[("Python files", "*.py")])
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as file:
                    pretty_history = json.dumps(self.history, indent=4, ensure_ascii=False, cls=BytesEncoder)
                    file.write(f"history={pretty_history}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save context: {str(e)}")

    def format_content_for_display(self, content):
        """Format content for display in the tree view."""
        return content.replace("\n", " ")[:256]

    def update_tree_view(self):
        self.tree.delete(*self.tree.get_children())
        for item in self.history:
            sequence = item.get("sequence")
            full_content = item["parts"][0]
            content = self.format_content_for_display(full_content)
            content_size = len(full_content)
            self.tree.insert("", tk.END, values=(item["role"], sequence, content_size, content))
        self.perform_search()  # Re-apply search after updating tree view

    def add_task_to_queue(self, tk_command):
        self.queue.put(tk_command)

async def listen_to_queue(app):
    try:
        while not app.stopped:
            queue = app.queue

            # Check if there's a task in the queue
            if not queue.empty():
                task = queue.get()
                # Schedule the Tk command to run on the main thread
                app.root.after(0, task)  # Run task in the Tkinter main loop
            await asyncio.sleep(0.1)  # Small delay to prevent tight looping
    except:
        return

if __name__ == "__main__":
    root = tk.Tk()
    app = LLMControlUI(root, Queue())

    main_loop = asyncio.get_event_loop_policy().get_event_loop()
    asyncio.run_coroutine_threadsafe(listen_to_queue(app), main_loop)
    async_mainloop(root)

    # Stop threads
    if app.zmq_context:
        app.zmq_publisher.close()
        app.zmq_subscriber.close()
        app.zmq_context.term()
