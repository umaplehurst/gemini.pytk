# /// script
# dependencies = [
#   "async-tkinter-loop",
#   "google-generativeai",
#   "openai",
# ]
# ///

from dotenv import load_dotenv
load_dotenv(verbose=True, override=True)

from user_ui_model import UserUIModel

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from tkinter import StringVar

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
        self.tree = ttk.Treeview(left_frame, columns=("Role", "Sequence", "Content"), show="headings")
        self.tree.heading("Role", text="Role")
        self.tree.heading("Sequence", text="Sequence")
        self.tree.heading("Content", text="Content")
        self.tree.column("Role", minwidth=75, width=75, stretch=False)
        self.tree.column("Sequence", minwidth=75, width=75, stretch=False)
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
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        paned_window.add(right_frame)

        # Create preview text widget
        self.preview_text = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, width=50)
        self.preview_text.pack(fill=tk.BOTH, expand=True)

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

        # Create Settings menu
        self.settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=self.settings_menu)

        # Dynamically create menu items for knobs
        self.create_knob_menu_items()

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

    def update_preview(self, event):
        selected_items = self.tree.selection()
        if selected_items:
            item = selected_items[0]  # Get the first selected item
            item_id = self.tree.index(item)
            sequence = self.history[item_id].get("sequence", "N/A")
            role = self.history[item_id]["role"]
            content = self.history[item_id]["parts"][0]
            self.preview_text.delete("1.0", tk.END)
            self.preview_text.insert(tk.END, f"Sequence: {sequence}\nRole: {role}\nContent:\n\n{content}")
        else:
            self.preview_text.delete("1.0", tk.END)

    # FIXME: We need to change these menu items depending on Gemini / Llama etc.
    # Because the same parameters are not directly equivalent between LLM species
    def create_knob_menu_items(self):
        for key, knob in self.ui_model.get_knobs().items():
            ui_component = knob.get_ui_component()
            if ui_component["type"] == "slider":
                self.create_slider_menu_item(key, ui_component)
            elif ui_component["type"] == "dropdown":
                self.create_dropdown_menu_item(key, ui_component)
            elif ui_component["type"] == "checkbox":
                self.create_checkbox_menu_item(key, ui_component)

    def create_slider_menu_item(self, key, ui_component):
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

    def create_dropdown_menu_item(self, key, ui_component):
        value = tk.StringVar(value=ui_component["value"])

        def update_value(*args):
            self.ui_model.get_knobs()[key].set_value(value.get())

        value.trace("w", update_value)

        dropdown_menu = tk.Menu(self.settings_menu, tearoff=0)
        for option in ui_component["options"]:
            dropdown_menu.add_radiobutton(label=option, variable=value, value=option)

        self.settings_menu.add_cascade(label=ui_component["name"], menu=dropdown_menu)

    def create_checkbox_menu_item(self, key, ui_component):
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
            self.tree.item(item, values=(role, sequence, new_content))
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
            self.tree.insert("", tk.END, values=("user", my_seq, displayed_message))
            self.input_box.delete("1.0", tk.END)

            # Update status
            self.status_var.set("Status: RUNNING")
            self.root.update()

            # Get LLM response
            self.chat_session = self.ui_model.generate_chat_session(self.history)
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
            self.tree.insert("", tk.END, values=("model", my_seq, displayed_response))

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
            content = self.format_content_for_display(item["parts"][0])
            self.tree.insert("", tk.END, values=(item["role"], sequence, content))
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
