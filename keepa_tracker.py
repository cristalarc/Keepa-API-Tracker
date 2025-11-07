"""
Keepa API Tracker - Main Application
This is the main entry point for the unified Keepa API tracking application.
It provides a menu-driven interface to access different analysis tools.
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from dotenv import load_dotenv
import pyautogui
import json
from buybox_analyzer import BuyboxAnalyzer
from sales_rank_module import SalesRankAnalyzer
from asin_manager import (
    load_all_asin_lists, save_asin_lists, validate_asin_list,
    add_asins_to_saved_list, load_saved_asins
)


# Load API key from .env
load_dotenv('.env.local')
KEEPA_API_KEY = os.getenv('Keepa_API_KEY')

# Validate that API key was loaded
if not KEEPA_API_KEY:
    print("Error: Keepa_API_KEY not found in .env.local file.")
    print("Please ensure your .env.local file contains: Keepa_API_KEY=your_api_key_here")
    exit(1)


class KeepaTrackerApp:
    """
    Main application class for the Keepa API Tracker.
    This class manages the main menu and coordinates between different analyzers.
    """
    
    def __init__(self):
        """Initialize the main application"""
        self.root = None
        self.buybox_analyzer = BuyboxAnalyzer(KEEPA_API_KEY)
        self.sales_rank_analyzer = SalesRankAnalyzer(KEEPA_API_KEY)
    
    def create_main_menu(self):
        """
        Creates and displays the main menu window.
        This is the central hub where users can select which analysis tool to use.
        """
        mouse_x, mouse_y = pyautogui.position()
        
        # Create the main window
        self.root = tk.Tk()
        self.root.title("Keepa API Tracker")
        self.root.geometry(f'1000x1000+{mouse_x}+{mouse_y}')

        # Center the window on screen
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (1000 // 2)
        y = (self.root.winfo_screenheight() // 2) - (1000 // 2)
        self.root.geometry(f'1000x1000+{x}+{y}')
        
        # Make window stay on top initially, then allow normal behavior
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after_idle(lambda: self.root.attributes('-topmost', False))
        
        # Create main frame
        main_frame = ttk.Frame(self.root, padding="30")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(
            main_frame, 
            text="Keepa API Tracker", 
            font=("Arial", 24, "bold")
        )
        title_label.pack(pady=(0, 30))
        
        # Subtitle
        subtitle_label = ttk.Label(
            main_frame, 
            text="Select an analysis tool:", 
            font=("Arial", 12)
        )
        subtitle_label.pack(pady=(0, 20))
        
        # Create button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=20)
        
        # Buybox Analyzer Button
        buybox_btn = ttk.Button(
            button_frame,
            text="Buybox Analyzer",
            command=self.run_buybox_analyzer,
            width=25,
            style="Accent.TButton"
        )
        buybox_btn.pack(pady=10)
        
        # Add tooltip/description for buybox analyzer
        buybox_desc = ttk.Label(
            button_frame,
            text="Analyze Amazon buybox ownership percentages",
            font=("Arial", 9),
            foreground="gray"
        )
        buybox_desc.pack(pady=(0, 10))

        # Current Buybox Owners Button
        current_owners_btn = ttk.Button(
            button_frame,
            text="Current Buybox Owners",
            command=self.run_current_buybox_owners,
            width=25
        )
        current_owners_btn.pack(pady=10)

        # Add tooltip/description for current owners
        current_owners_desc = ttk.Label(
            button_frame,
            text="Get current buybox owner for list of ASINs",
            font=("Arial", 9),
            foreground="gray"
        )
        current_owners_desc.pack(pady=(0, 10))

        # Sales Rank Analyzer Button
        sales_rank_btn = ttk.Button(
            button_frame,
            text="Sales Rank Analyzer",
            command=self.run_sales_rank_analyzer,
            width=25
        )
        sales_rank_btn.pack(pady=10)
        
        # Add tooltip/description for sales rank analyzer
        sales_rank_desc = ttk.Label(
            button_frame,
            text="Analyze product sales rank trends",
            font=("Arial", 9),
            foreground="gray"
        )
        sales_rank_desc.pack(pady=(0, 10))

        # ASIN Manager Button
        asin_manager_btn = ttk.Button(
            button_frame,
            text="ASIN Manager",
            command=self.run_asin_manager,
            width=25
        )
        asin_manager_btn.pack(pady=10)

        # Add tooltip/description for ASIN manager
        asin_manager_desc = ttk.Label(
            button_frame,
            text="Manage, import, and export ASIN lists",
            font=("Arial", 9),
            foreground="gray"
        )
        asin_manager_desc.pack(pady=(0, 10))

        # Exit Button
        exit_btn = ttk.Button(
            button_frame,
            text="Exit",
            command=self.exit_application,
            width=25
        )
        exit_btn.pack(pady=(20, 0))
        
        # Add footer
        footer_label = ttk.Label(
            main_frame,
            text="All tools will return to this menu when finished",
            font=("Arial", 8),
            foreground="gray"
        )
        footer_label.pack(side=tk.BOTTOM, pady=(20, 0))
    
    def run_buybox_analyzer(self):
        """
        Runs the buybox analyzer tool.
        After completion, returns to the main menu.
        """
        try:
            # Get user input for buybox analysis
            user_input = self.buybox_analyzer.get_user_input(parent_window=self.root)
            
            if user_input is None:
                # User cancelled, return to menu
                return
            
            asins, year, months, export_csv = user_input
            
            # Process and display results
            self.buybox_analyzer.process_and_display_results(
                asins, year, months, export_csv, parent_window=self.root
            )
            
            # Return to menu after results window is closed
            messagebox.showinfo(
                "Complete", 
                "Buybox analysis complete. Returning to main menu.",
                parent=self.root
            )
            
        except Exception as e:
            messagebox.showerror(
                "Error",
                f"An error occurred during buybox analysis:\n{str(e)}",
                parent=self.root
            )
    
    def run_current_buybox_owners(self):
        """
        Runs the current buybox owners tool.
        After completion, returns to the main menu.
        """
        try:
            # Get user input for current owner lookup
            user_input = self.buybox_analyzer.get_current_owners_input(parent_window=self.root)

            if user_input is None:
                # User cancelled, return to menu
                return

            asins, export_csv = user_input

            # Process and display results
            self.buybox_analyzer.process_and_display_current_owners(
                asins, export_csv, parent_window=self.root
            )

            # Return to menu after results window is closed
            messagebox.showinfo(
                "Complete",
                "Current buybox owner lookup complete. Returning to main menu.",
                parent=self.root
            )

        except Exception as e:
            messagebox.showerror(
                "Error",
                f"An error occurred during current owner lookup:\n{str(e)}",
                parent=self.root
            )

    def run_sales_rank_analyzer(self):
        """
        Runs the sales rank analyzer tool.
        After completion, returns to the main menu.
        """
        try:
            # Get user input for sales rank analysis
            user_input = self.sales_rank_analyzer.get_user_input(parent_window=self.root)

            if user_input is None:
                # User cancelled, return to menu
                return

            asin, days, export_csv = user_input

            # Process and display results
            self.sales_rank_analyzer.process_and_display_results(
                asin, days, export_csv, parent_window=self.root
            )

            # Return to menu after results window is closed
            messagebox.showinfo(
                "Complete",
                "Sales rank analysis complete. Returning to main menu.",
                parent=self.root
            )

        except Exception as e:
            messagebox.showerror(
                "Error",
                f"An error occurred during sales rank analysis:\n{str(e)}",
                parent=self.root
            )
    
    def run_asin_manager(self):
        """
        Opens the ASIN Manager window.
        Allows users to manage, import, and export ASIN lists.
        """
        try:
            # Create ASIN Manager window
            manager_window = tk.Toplevel(self.root)
            manager_window.title("ASIN Manager")
            manager_window.geometry("900x700")
            manager_window.transient(self.root)

            # Center the window
            manager_window.update_idletasks()
            x = (manager_window.winfo_screenwidth() // 2) - (900 // 2)
            y = (manager_window.winfo_screenheight() // 2) - (700 // 2)
            manager_window.geometry(f'900x700+{x}+{y}')

            # Load current ASIN lists
            lists_data = load_all_asin_lists()

            # Create main frame
            main_frame = ttk.Frame(manager_window, padding="20")
            main_frame.pack(fill=tk.BOTH, expand=True)

            # Title
            ttk.Label(main_frame, text="ASIN Manager", font=("Arial", 18, "bold")).pack(pady=(0, 20))

            # Create notebook for tabs
            notebook = ttk.Notebook(main_frame)
            notebook.pack(fill=tk.BOTH, expand=True)

            # ===== Add ASINs Tab =====
            add_frame = ttk.Frame(notebook, padding="10")
            notebook.add(add_frame, text="Add ASINs")

            # List selection for adding ASINs
            list_selection_frame = ttk.Frame(add_frame)
            list_selection_frame.pack(fill=tk.X, pady=(0, 10))

            ttk.Label(list_selection_frame, text="Add to list:").pack(side=tk.LEFT)
            list_names = list(lists_data.keys()) if lists_data else ["Default List"]
            selected_list_var = tk.StringVar(value=list_names[0] if list_names else "Default List")
            list_combobox = ttk.Combobox(list_selection_frame, textvariable=selected_list_var, values=list_names, state="readonly", width=25)
            list_combobox.pack(side=tk.LEFT, padx=(10, 0))

            def create_new_list():
                """Create a new ASIN list"""
                new_name = simpledialog.askstring("New List", "Enter name for new list:", parent=manager_window)
                if new_name and new_name.strip():
                    new_name = new_name.strip()
                    if new_name in lists_data:
                        messagebox.showerror("Error", "List name already exists.", parent=manager_window)
                        return

                    lists_data[new_name] = {'asins': [], 'description': ''}
                    if add_asins_to_saved_list([], new_name):
                        list_names = list(load_all_asin_lists().keys())
                        list_combobox['values'] = list_names
                        selected_list_var.set(new_name)
                        messagebox.showinfo("Success", f"Created new list: {new_name}", parent=manager_window)
                        refresh_all_lists()
                    else:
                        messagebox.showerror("Error", "Failed to create new list.", parent=manager_window)

            ttk.Button(list_selection_frame, text="New List", command=create_new_list).pack(side=tk.LEFT, padx=(10, 0))

            # Add ASINs section
            add_asins_frame = ttk.LabelFrame(add_frame, text="Add New ASINs", padding="10")
            add_asins_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

            ttk.Label(add_asins_frame, text="Paste ASINs (comma, space, or newline separated):").pack(anchor=tk.W)

            asin_text = tk.Text(add_asins_frame, height=10, width=70)
            asin_text.pack(fill=tk.BOTH, expand=True, pady=(5, 10))

            def add_asins():
                """Add ASINs from text input"""
                text_content = asin_text.get("1.0", tk.END).strip()
                valid_asins, error_msg = validate_asin_list(text_content)

                if error_msg:
                    messagebox.showerror("Validation Error", error_msg, parent=manager_window)
                    return

                if not valid_asins:
                    messagebox.showwarning("No ASINs", "No valid ASINs found in input.", parent=manager_window)
                    return

                selected_list = selected_list_var.get()
                total_asins, new_asins = add_asins_to_saved_list(valid_asins, selected_list)
                messagebox.showinfo("Success", f"Added {new_asins} new ASINs to '{selected_list}'. Total in list: {total_asins}", parent=manager_window)

                refresh_all_lists()
                asin_text.delete("1.0", tk.END)

            ttk.Button(add_asins_frame, text="Add ASINs", command=add_asins, style="Accent.TButton").pack(pady=(0, 10))

            # ===== Manage Lists Tab =====
            manage_frame = ttk.Frame(notebook, padding="10")
            notebook.add(manage_frame, text="Manage Lists")

            # Lists overview
            lists_frame = ttk.LabelFrame(manage_frame, text="ASIN Lists", padding="10")
            lists_frame.pack(fill=tk.BOTH, expand=True)

            # Create treeview for lists
            columns = ('List Name', 'ASIN Count', 'Description')
            lists_tree = ttk.Treeview(lists_frame, columns=columns, show='headings', height=20)

            for col in columns:
                lists_tree.heading(col, text=col)
                lists_tree.column(col, width=200)

            lists_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            # Scrollbar for treeview
            tree_scrollbar = ttk.Scrollbar(lists_frame, orient=tk.VERTICAL, command=lists_tree.yview)
            lists_tree.configure(yscrollcommand=tree_scrollbar.set)
            tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            def refresh_lists_tree():
                """Refresh the lists treeview"""
                for item in lists_tree.get_children():
                    lists_tree.delete(item)

                lists_data = load_all_asin_lists()
                for list_name, list_data in lists_data.items():
                    asin_count = len(list_data.get('asins', []))
                    description = list_data.get('description', '')
                    lists_tree.insert('', tk.END, values=(list_name, asin_count, description))

            def remove_selected_list():
                """Remove selected list"""
                selection = lists_tree.selection()
                if not selection:
                    messagebox.showwarning("No Selection", "Please select a list to remove.", parent=manager_window)
                    return

                selected_item = lists_tree.item(selection[0])
                list_name = selected_item['values'][0]

                if messagebox.askyesno("Confirm", f"Are you sure you want to remove the list '{list_name}'?", parent=manager_window):
                    lists_data = load_all_asin_lists()
                    if list_name in lists_data:
                        del lists_data[list_name]
                        if save_asin_lists(lists_data):
                            messagebox.showinfo("Success", f"Removed list: {list_name}", parent=manager_window)
                            refresh_all_lists()
                        else:
                            messagebox.showerror("Error", "Failed to remove list.", parent=manager_window)

            def clear_selected_list():
                """Clear ASINs from selected list"""
                selection = lists_tree.selection()
                if not selection:
                    messagebox.showwarning("No Selection", "Please select a list to clear.", parent=manager_window)
                    return

                selected_item = lists_tree.item(selection[0])
                list_name = selected_item['values'][0]

                if messagebox.askyesno("Confirm", f"Are you sure you want to clear all ASINs from '{list_name}'?", parent=manager_window):
                    lists_data = load_all_asin_lists()
                    if list_name in lists_data:
                        lists_data[list_name]['asins'] = []
                        if save_asin_lists(lists_data):
                            messagebox.showinfo("Success", f"Cleared list: {list_name}", parent=manager_window)
                            refresh_all_lists()
                        else:
                            messagebox.showerror("Error", "Failed to clear list.", parent=manager_window)

            def export_selected_lists():
                """Export selected or all lists to JSON file"""
                lists_data = load_all_asin_lists()
                if not lists_data:
                    messagebox.showwarning("No Lists", "No ASIN lists to export.", parent=manager_window)
                    return

                # Ask if user wants to export all or selected
                export_all = messagebox.askyesno(
                    "Export Options",
                    "Export ALL lists?\n\nYes = Export all lists\nNo = Export selected list only",
                    parent=manager_window
                )

                export_data = {}

                if export_all:
                    export_data = lists_data
                else:
                    # Get selected list
                    selection = lists_tree.selection()
                    if not selection:
                        messagebox.showwarning("No Selection", "Please select a list to export.", parent=manager_window)
                        return

                    selected_item = lists_tree.item(selection[0])
                    list_name = selected_item['values'][0]
                    export_data = {list_name: lists_data[list_name]}

                # Save to file
                save_path = filedialog.asksaveasfilename(
                    title='Export ASIN Lists',
                    defaultextension='.json',
                    filetypes=[('JSON files', '*.json'), ('All files', '*.*')],
                    parent=manager_window
                )

                if save_path:
                    try:
                        with open(save_path, 'w') as f:
                            json.dump(export_data, f, indent=2)

                        list_count = len(export_data)
                        total_asins = sum(len(data.get('asins', [])) for data in export_data.values())
                        messagebox.showinfo(
                            "Export Successful",
                            f"Exported {list_count} list(s) with {total_asins} total ASINs to:\n{save_path}",
                            parent=manager_window
                        )
                    except Exception as e:
                        messagebox.showerror("Export Failed", f"Failed to export lists: {str(e)}", parent=manager_window)

            def import_lists():
                """Import ASIN lists from JSON file"""
                file_path = filedialog.askopenfilename(
                    title='Import ASIN Lists',
                    filetypes=[('JSON files', '*.json'), ('All files', '*.*')],
                    parent=manager_window
                )

                if not file_path:
                    return

                try:
                    with open(file_path, 'r') as f:
                        imported_data = json.load(f)

                    if not isinstance(imported_data, dict):
                        messagebox.showerror("Invalid Format", "Invalid file format. Expected JSON dictionary.", parent=manager_window)
                        return

                    # Load current lists
                    current_lists = load_all_asin_lists()

                    # Check for conflicts
                    conflicts = [name for name in imported_data.keys() if name in current_lists]

                    if conflicts:
                        merge_option = messagebox.askyesnocancel(
                            "List Conflicts",
                            f"The following lists already exist:\n{', '.join(conflicts)}\n\n"
                            "Yes = Merge (add new ASINs to existing lists)\n"
                            "No = Replace (overwrite existing lists)\n"
                            "Cancel = Skip conflicting lists",
                            parent=manager_window
                        )

                        if merge_option is None:  # Cancel
                            # Skip conflicts, only import new lists
                            for name in conflicts:
                                del imported_data[name]
                        elif merge_option:  # Yes - Merge
                            for name in conflicts:
                                existing_asins = set(current_lists[name].get('asins', []))
                                new_asins = set(imported_data[name].get('asins', []))
                                merged_asins = list(existing_asins | new_asins)
                                imported_data[name]['asins'] = merged_asins
                        # else: No - Replace (keep imported_data as is)

                    # Merge with current lists
                    current_lists.update(imported_data)

                    # Save merged data
                    if save_asin_lists(current_lists):
                        list_count = len(imported_data)
                        total_asins = sum(len(data.get('asins', [])) for data in imported_data.values())
                        messagebox.showinfo(
                            "Import Successful",
                            f"Imported {list_count} list(s) with {total_asins} total ASINs.",
                            parent=manager_window
                        )
                        refresh_all_lists()
                    else:
                        messagebox.showerror("Import Failed", "Failed to save imported lists.", parent=manager_window)

                except json.JSONDecodeError:
                    messagebox.showerror("Invalid File", "File is not valid JSON.", parent=manager_window)
                except Exception as e:
                    messagebox.showerror("Import Failed", f"Failed to import lists: {str(e)}", parent=manager_window)

            # Buttons for list management
            list_buttons_frame = ttk.Frame(manage_frame)
            list_buttons_frame.pack(fill=tk.X, pady=(10, 0))

            ttk.Button(list_buttons_frame, text="Remove Selected", command=remove_selected_list).pack(side=tk.LEFT, padx=(0, 5))
            ttk.Button(list_buttons_frame, text="Clear Selected", command=clear_selected_list).pack(side=tk.LEFT, padx=(0, 5))
            ttk.Button(list_buttons_frame, text="Export Lists", command=export_selected_lists, style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 5))
            ttk.Button(list_buttons_frame, text="Import Lists", command=import_lists, style="Accent.TButton").pack(side=tk.LEFT)

            # ===== Edit List Tab =====
            edit_list_frame = ttk.Frame(notebook, padding="10")
            notebook.add(edit_list_frame, text="Edit List")

            # List selection for editing
            edit_selection_frame = ttk.Frame(edit_list_frame)
            edit_selection_frame.pack(fill=tk.X, pady=(0, 10))

            ttk.Label(edit_selection_frame, text="Select list to edit:").pack(side=tk.LEFT)
            edit_list_names = list(lists_data.keys()) if lists_data else []
            edit_selected_list_var = tk.StringVar(value=edit_list_names[0] if edit_list_names else "")
            edit_list_combobox = ttk.Combobox(edit_selection_frame, textvariable=edit_selected_list_var, values=edit_list_names, state="readonly", width=25)
            edit_list_combobox.pack(side=tk.LEFT, padx=(10, 0))

            def rename_list():
                """Rename the selected list"""
                current_name = edit_selected_list_var.get()
                if not current_name:
                    messagebox.showwarning("No Selection", "Please select a list to rename.", parent=manager_window)
                    return

                new_name = simpledialog.askstring("Rename List", f"Enter new name for '{current_name}':",
                                                  initialvalue=current_name, parent=manager_window)
                if new_name and new_name.strip():
                    new_name = new_name.strip()
                    if new_name == current_name:
                        return

                    lists_data = load_all_asin_lists()
                    if new_name in lists_data:
                        messagebox.showerror("Error", "A list with this name already exists.", parent=manager_window)
                        return

                    # Rename the list
                    lists_data[new_name] = lists_data.pop(current_name)
                    if save_asin_lists(lists_data):
                        messagebox.showinfo("Success", f"Renamed '{current_name}' to '{new_name}'", parent=manager_window)
                        edit_selected_list_var.set(new_name)
                        refresh_all_lists()
                        refresh_edit_list()
                    else:
                        messagebox.showerror("Error", "Failed to rename list.", parent=manager_window)

            ttk.Button(edit_selection_frame, text="Rename List", command=rename_list).pack(side=tk.LEFT, padx=(10, 0))

            # List description
            edit_desc_frame = ttk.Frame(edit_list_frame)
            edit_desc_frame.pack(fill=tk.X, pady=(0, 10))

            ttk.Label(edit_desc_frame, text="Description:").pack(side=tk.LEFT)
            edit_desc_var = tk.StringVar()
            edit_desc_entry = ttk.Entry(edit_desc_frame, textvariable=edit_desc_var, width=50)
            edit_desc_entry.pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)

            def update_description():
                """Update the list description"""
                list_name = edit_selected_list_var.get()
                if not list_name:
                    return

                lists_data = load_all_asin_lists()
                if list_name in lists_data:
                    lists_data[list_name]['description'] = edit_desc_var.get()
                    if save_asin_lists(lists_data):
                        messagebox.showinfo("Success", f"Updated description for '{list_name}'", parent=manager_window)
                        refresh_all_lists()
                    else:
                        messagebox.showerror("Error", "Failed to update description.", parent=manager_window)

            ttk.Button(edit_desc_frame, text="Update", command=update_description).pack(side=tk.LEFT, padx=(10, 0))

            # ASINs in selected list
            edit_asins_frame = ttk.LabelFrame(edit_list_frame, text="ASINs in List", padding="10")
            edit_asins_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

            # Create listbox for ASINs in the selected list
            edit_listbox_frame = ttk.Frame(edit_asins_frame)
            edit_listbox_frame.pack(fill=tk.BOTH, expand=True)

            edit_asin_listbox = tk.Listbox(edit_listbox_frame, selectmode=tk.EXTENDED, height=20)
            edit_asin_scrollbar = ttk.Scrollbar(edit_listbox_frame, orient=tk.VERTICAL, command=edit_asin_listbox.yview)
            edit_asin_listbox.configure(yscrollcommand=edit_asin_scrollbar.set)

            edit_asin_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            edit_asin_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            # ASIN count label
            edit_count_label = ttk.Label(edit_asins_frame, text="ASINs: 0")
            edit_count_label.pack(pady=(5, 0))

            def refresh_edit_list():
                """Refresh the edit list display"""
                list_name = edit_selected_list_var.get()
                edit_asin_listbox.delete(0, tk.END)
                edit_desc_var.set("")

                if not list_name:
                    edit_count_label.config(text="ASINs: 0")
                    return

                lists_data = load_all_asin_lists()
                if list_name in lists_data:
                    asins = lists_data[list_name].get('asins', [])
                    description = lists_data[list_name].get('description', '')
                    edit_desc_var.set(description)

                    for asin in sorted(asins):
                        edit_asin_listbox.insert(tk.END, asin)

                    edit_count_label.config(text=f"ASINs: {len(asins)}")
                else:
                    edit_count_label.config(text="ASINs: 0")

            def remove_selected_asins_from_list():
                """Remove selected ASINs from the current list"""
                list_name = edit_selected_list_var.get()
                if not list_name:
                    messagebox.showwarning("No List", "Please select a list.", parent=manager_window)
                    return

                selection = edit_asin_listbox.curselection()
                if not selection:
                    messagebox.showwarning("No Selection", "Please select ASINs to remove.", parent=manager_window)
                    return

                selected_asins = [edit_asin_listbox.get(i) for i in selection]

                if messagebox.askyesno("Confirm",
                                      f"Remove {len(selected_asins)} ASIN(s) from '{list_name}'?",
                                      parent=manager_window):
                    lists_data = load_all_asin_lists()
                    if list_name in lists_data:
                        for asin in selected_asins:
                            if asin in lists_data[list_name]['asins']:
                                lists_data[list_name]['asins'].remove(asin)

                        if save_asin_lists(lists_data):
                            messagebox.showinfo("Success",
                                              f"Removed {len(selected_asins)} ASIN(s) from '{list_name}'",
                                              parent=manager_window)
                            refresh_edit_list()
                            refresh_all_lists()
                        else:
                            messagebox.showerror("Error", "Failed to remove ASINs.", parent=manager_window)

            def add_asin_to_edit_list():
                """Add a single ASIN to the current list"""
                list_name = edit_selected_list_var.get()
                if not list_name:
                    messagebox.showwarning("No List", "Please select a list.", parent=manager_window)
                    return

                new_asin = simpledialog.askstring("Add ASIN",
                                                  f"Enter ASIN to add to '{list_name}':",
                                                  parent=manager_window)
                if new_asin and new_asin.strip():
                    new_asin = new_asin.strip().upper()

                    # Validate ASIN
                    from asin_manager import validate_asin
                    if not validate_asin(new_asin):
                        messagebox.showerror("Invalid ASIN",
                                           "ASIN must be exactly 10 alphanumeric characters.",
                                           parent=manager_window)
                        return

                    lists_data = load_all_asin_lists()
                    if list_name in lists_data:
                        if new_asin in lists_data[list_name]['asins']:
                            messagebox.showinfo("Duplicate",
                                              f"ASIN '{new_asin}' already exists in '{list_name}'",
                                              parent=manager_window)
                            return

                        lists_data[list_name]['asins'].append(new_asin)
                        if save_asin_lists(lists_data):
                            messagebox.showinfo("Success",
                                              f"Added '{new_asin}' to '{list_name}'",
                                              parent=manager_window)
                            refresh_edit_list()
                            refresh_all_lists()
                        else:
                            messagebox.showerror("Error", "Failed to add ASIN.", parent=manager_window)

            # Buttons for editing
            edit_buttons_frame = ttk.Frame(edit_asins_frame)
            edit_buttons_frame.pack(fill=tk.X, pady=(10, 0))

            ttk.Button(edit_buttons_frame, text="Add ASIN", command=add_asin_to_edit_list).pack(side=tk.LEFT, padx=(0, 5))
            ttk.Button(edit_buttons_frame, text="Remove Selected", command=remove_selected_asins_from_list).pack(side=tk.LEFT)

            # Bind list selection change
            def on_list_change(event):
                refresh_edit_list()

            edit_list_combobox.bind('<<ComboboxSelected>>', on_list_change)

            # ===== All ASINs Tab =====
            all_asins_frame = ttk.Frame(notebook, padding="10")
            notebook.add(all_asins_frame, text="All ASINs")

            asin_listbox_frame = ttk.Frame(all_asins_frame)
            asin_listbox_frame.pack(fill=tk.BOTH, expand=True)

            asin_listbox = tk.Listbox(asin_listbox_frame, selectmode=tk.SINGLE, height=25)
            asin_scrollbar = ttk.Scrollbar(asin_listbox_frame, orient=tk.VERTICAL, command=asin_listbox.yview)
            asin_listbox.configure(yscrollcommand=asin_scrollbar.set)

            asin_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            asin_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            def refresh_asin_list():
                """Refresh the ASIN listbox"""
                asin_listbox.delete(0, tk.END)
                current_asins = load_saved_asins()
                for asin in sorted(current_asins):
                    asin_listbox.insert(tk.END, asin)

            def remove_selected_asin():
                """Remove selected ASIN from all lists"""
                selection = asin_listbox.curselection()
                if not selection:
                    messagebox.showwarning("No Selection", "Please select an ASIN to remove.", parent=manager_window)
                    return

                selected_asin = asin_listbox.get(selection[0])
                lists_data = load_all_asin_lists()

                removed_from = []
                for list_name, list_data in lists_data.items():
                    if selected_asin in list_data.get('asins', []):
                        list_data['asins'].remove(selected_asin)
                        removed_from.append(list_name)

                if removed_from:
                    if save_asin_lists(lists_data):
                        messagebox.showinfo("Success", f"Removed ASIN {selected_asin} from: {', '.join(removed_from)}", parent=manager_window)
                        refresh_all_lists()
                    else:
                        messagebox.showerror("Error", "Failed to remove ASIN.", parent=manager_window)

            def clear_all_asins():
                """Clear all saved ASINs"""
                if messagebox.askyesno("Confirm", "Are you sure you want to remove all saved ASINs?", parent=manager_window):
                    if save_asin_lists({}):
                        messagebox.showinfo("Success", "All ASINs removed.", parent=manager_window)
                        refresh_all_lists()
                    else:
                        messagebox.showerror("Error", "Failed to clear ASINs.", parent=manager_window)

            # Buttons for ASIN management
            asin_buttons_frame = ttk.Frame(all_asins_frame)
            asin_buttons_frame.pack(fill=tk.X, pady=(10, 0))

            ttk.Button(asin_buttons_frame, text="Remove Selected ASIN", command=remove_selected_asin).pack(side=tk.LEFT, padx=(0, 10))
            ttk.Button(asin_buttons_frame, text="Clear All ASINs", command=clear_all_asins).pack(side=tk.LEFT)

            def refresh_all_lists():
                """Refresh all list displays"""
                refresh_lists_tree()
                refresh_asin_list()
                lists_data = load_all_asin_lists()
                list_names = list(lists_data.keys()) if lists_data else ["Default List"]
                list_combobox['values'] = list_names
                edit_list_combobox['values'] = list_names
                if selected_list_var.get() not in list_names:
                    selected_list_var.set(list_names[0] if list_names else "Default List")
                # Update Edit List tab if current selection is deleted/renamed
                if edit_selected_list_var.get() not in list_names:
                    edit_selected_list_var.set(list_names[0] if list_names else "Default List")
                    refresh_edit_list()

            # Initial load
            refresh_all_lists()

            # Close button
            ttk.Button(main_frame, text="Close", command=manager_window.destroy).pack(pady=(20, 0))

            # Wait for window to close
            manager_window.wait_window()

        except Exception as e:
            messagebox.showerror(
                "Error",
                f"An error occurred in ASIN Manager:\n{str(e)}",
                parent=self.root
            )

    def exit_application(self):
        """Exits the application"""
        self.root.destroy()
    
    def run(self):
        """
        Starts the main application loop.
        This is the entry point that displays the menu and handles user interactions.
        """
        self.create_main_menu()
        self.root.mainloop()


def main():
    """
    Main function to start the Keepa API Tracker application.
    This is the entry point when running the script directly.
    """
    print("Keepa API Tracker")
    print("=" * 30)
    print("Starting application...")
    
    # Create and run the application
    app = KeepaTrackerApp()
    app.run()


if __name__ == "__main__":
    main()

