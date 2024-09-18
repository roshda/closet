import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
import requests
import base64
import plotly.express as px

# --- Google Sheets API Setup ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
client = gspread.authorize(creds)

# Open the Google Sheets by name
spreadsheet = client.open("wardrobe")  # Ensure "wardrobe" matches your actual Google Sheet name
sheet_all = spreadsheet.worksheet("all")  # "all" sheet for all clothing items
sheet_log = spreadsheet.worksheet("log")  # "log" sheet for daily logs

# Load existing data from the Google Sheet "all"
def load_all_data():
    data = sheet_all.get_all_records()
    return pd.DataFrame(data)

# Load existing data from the Google Sheet "log"
def load_log_data():
    data = sheet_log.get_all_records()
    return pd.DataFrame(data)

df_all = load_all_data()
df_log = load_log_data()

# Create a directory for images if it doesn't exist
image_dir = "images"
if not os.path.exists(image_dir):
    os.makedirs(image_dir)

# Convert Google Drive link to a direct link for image download
def convert_drive_link_to_direct(link):
    if pd.isna(link) or not link:
        return None
    if "drive.google.com" in link:
        parts = link.split('/')
        if "d" in parts:
            file_id = parts[parts.index("d") + 1]
            return f"https://drive.google.com/uc?export=download&id={file_id}"
    return None

# Download images and save them locally
def download_image(url, filename):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(response.content)
            return filename
    except Exception as e:
        print(f"Failed to download {url}: {e}")
    return None

# Apply the conversion and downloading function to the "image" column
def download_images(df, image_dir):
    df['local_image_path'] = None
    for idx, row in df.iterrows():
        direct_link = convert_drive_link_to_direct(row['image'])
        if direct_link:
            local_filename = os.path.join(image_dir, f"{row['Name'].replace(' ', '_')}.jpg")
            if not os.path.exists(local_filename):
                local_image_path = download_image(direct_link, local_filename)
                df.at[idx, 'local_image_path'] = local_image_path
            else:
                df.at[idx, 'local_image_path'] = local_filename
    return df

df_all = download_images(df_all, image_dir)

# Convert image to base64 for embedding in HTML
def convert_to_base64(path):
    with open(path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()

# Convert Image file paths to HTML for rendering in the DataFrame
def path_to_image_html(path):
    if path:
        return f'<img src="data:image/jpeg;base64,{convert_to_base64(path)}" width="100" height="auto">'
    return "No image available"

# Sidebar for showing details of the selected item
def show_details_in_sidebar(item):
    st.sidebar.write("## Item Details")
    st.sidebar.write(f"**Name:** {item['Name']}")
    st.sidebar.write(f"**Brand:** {item['Brand']}")
    st.sidebar.write(f"**Category:** {item['Category']}")
    st.sidebar.write(f"**Color:** {item['Color']}")
    st.sidebar.write(f"**Material:** {item['Material']}")
    st.sidebar.write(f"**Price:** ${item['Price']:.2f}")

# Interactive Image Grid to Select Item
def display_images_in_grid(df, max_columns=7):
    num_items = len(df)
    num_rows = (num_items // max_columns) + (num_items % max_columns > 0)

    for row in range(num_rows):
        cols = st.columns(max_columns)
        for col_idx in range(max_columns):
            item_idx = row * max_columns + col_idx
            if item_idx < num_items:
                item = df.iloc[item_idx]
                with cols[col_idx]:
                    # Display image
                    st.markdown(path_to_image_html(item['local_image_path']), unsafe_allow_html=True)
                    # Clickable title to filter data, using a unique key based on item name
                    if st.button(f"{item['Name']}", key=f"{item_idx}-{item['Name']}"):
                        st.session_state['selected_items'] = [item['Name']]  # Focus on a specific item

# Initialize session state for selected items
if 'selected_items' not in st.session_state:
    st.session_state['selected_items'] = list(df_all['Name'])  # Start with all items selected

# Filters and Clothing Items Display
st.write("## Roshni's Closet")
col1, col2, col3, col4 = st.columns(4)

# Button to reset selection to all items (moved here)
if st.button("Show All Items"):
    st.session_state['selected_items'] = list(df_all['Name'])

# Define the selectboxes and ensure they are initialized
with col1:
    selected_category = st.selectbox("Select Category", options=["All"] + list(df_all["Category"].unique()), index=0)
with col2:
    selected_color = st.selectbox("Select Color", options=["All"] + list(df_all["Color"].unique()), index=0)
with col3:
    selected_brand = st.selectbox("Select Brand", options=["All"] + list(df_all["Brand"].unique()), index=0)
with col4:
    selected_material = st.selectbox("Select Material", options=["All"] + list(df_all["Material"].unique()), index=0)

# Filter data based on selection
df_filtered = df_all.copy()

if selected_category and selected_category != "All":
    df_filtered = df_filtered[df_filtered["Category"] == selected_category]

if selected_color and selected_color != "All":
    df_filtered = df_filtered[df_filtered["Color"] == selected_color]

if selected_brand and selected_brand != "All":
    df_filtered = df_filtered[df_filtered["Brand"] == selected_brand]

if selected_material and selected_material != "All":
    df_filtered = df_filtered[df_filtered["Material"] == selected_material]

# Display All Clothes as a Grid
st.write("## All Clothing Items")
display_images_in_grid(df_filtered)

# Load selected items from the session state
selected_items = st.session_state['selected_items']

# Filter data for selected items
df_selected = df_all[df_all['Name'].isin(selected_items)]

# If a specific item(s) is selected, display its details and filter graphs
if len(selected_items) == 1:
    selected_item_data = df_selected.iloc[0]
    show_details_in_sidebar(selected_item_data)

# Calculate Cost Per Wear and Wear Trends for the selected items
def process_log_data(log_df, item_names):
    log_df_long = log_df.melt(id_vars=['date'], var_name='Item Number', value_name='Item').dropna()
    log_df_long['date'] = pd.to_datetime(log_df_long['date'])
    log_df_long = log_df_long[log_df_long['Item'].isin(item_names)]  # Filter only for the selected items
    wear_counts = log_df_long.groupby('Item').size().reset_index(name='Wear Count')  # Accurate wear counts
    return log_df_long, wear_counts

df_log_long, wear_counts = process_log_data(df_log, selected_items)

def calculate_cost_per_wear(all_df, wear_counts_df):
    merged = pd.merge(all_df, wear_counts_df, left_on="Name", right_on="Item", how="left").fillna(0)
    merged["Wear Count"] = merged["Wear Count"].replace(0, 1)  # Prevent division by zero
    merged["Cost Per Wear"] = merged["Price"] / merged["Wear Count"]
    return merged[["Name", "Price", "Wear Count", "Cost Per Wear"]]

cost_per_wear_df = calculate_cost_per_wear(df_all, wear_counts)

# Prepare Data for Graphs
df_wears_filtered = df_log_long.groupby(['date', 'Item']).size().reset_index(name='Wears')
df_wears_filtered['date'] = pd.to_datetime(df_wears_filtered['date'])
df_wears_filtered['Cumulative Wears'] = df_wears_filtered.groupby('Item')['Wears'].cumsum()

# Insert this section after df_wears_filtered and before the "Overall Wear Statistics" section

# Create tabs for the first three Plotly graphs
tab_total_wears, tab_cost_per_wear, tab_wears_by_month = st.tabs(["Total Wears Over Time", "Cost Per Wear Over Time", "Wears by Month"])

# Tab 1: Total Wears Over Time
with tab_total_wears:
    fig_total_wears = px.line(
        df_wears_filtered, 
        x='date', 
        y='Cumulative Wears', 
        color='Item', 
        markers=True, 
        title='Total Wears Over Time',
        labels={'date': 'Date', 'Cumulative Wears': 'Cumulative Wears'}
    )
    st.plotly_chart(fig_total_wears, use_container_width=True)

# Tab 2: Cost Per Wear Over Time
with tab_cost_per_wear:
    df_log_long['Wears'] = 1  # Each log entry indicates one wear

    # Update Cost Per Wear calculation for selected item(s)
    cost_per_wear_over_time = df_log_long.merge(cost_per_wear_df[['Name', 'Price']], left_on='Item', right_on='Name')
    cost_per_wear_over_time['Cumulative Wears'] = cost_per_wear_over_time.groupby('Item')['Wears'].cumsum()

    # Reverse cumulative wears calculation for Cost Per Wear
    cost_per_wear_over_time['Reverse Wears'] = cost_per_wear_over_time.groupby('Item')['Wears'].transform(lambda x: x[::-1].cumsum())
    cost_per_wear_over_time['Cost Per Wear'] = cost_per_wear_over_time['Price'] / cost_per_wear_over_time['Reverse Wears']
    cost_per_wear_over_time = cost_per_wear_over_time[cost_per_wear_over_time['Wears'] > 0]  # Only show points where there's a wear

    fig_cost_per_wear = px.line(
        cost_per_wear_over_time, 
        x='date', 
        y='Cost Per Wear', 
        color='Item', 
        title='Cost Per Wear Over Time',
        labels={'date': 'Date', 'Cost Per Wear': 'Cost Per Wear'}
    )
    st.plotly_chart(fig_cost_per_wear, use_container_width=True)

# Tab 3: Wears by Month
with tab_wears_by_month:
    df_wears_filtered['Month'] = df_wears_filtered['date'].dt.strftime('%b')  # Convert to month names
    df_wears_filtered['Month'] = pd.Categorical(df_wears_filtered['Month'], categories=['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], ordered=True)
    wears_by_month = df_wears_filtered.groupby(['Month', 'Item'])['Wears'].sum().reset_index()

    fig_wears_by_month = px.line(
        wears_by_month, 
        x='Month', 
        y='Wears', 
        color='Item', 
        markers=True, 
        title='Wears by Month',
        labels={'Month': 'Month', 'Wears': 'Number of Wears'}
    )
    st.plotly_chart(fig_wears_by_month, use_container_width=True)


# Additional Graphs and Overall Wear Statistics
st.write("## Overall Wear Statistics")

# Create tabs for Wears and Items
tab1, tab2, tab3, tab4 = st.tabs(["Wears by Material", "Wears by Category", "Items by Material", "Items by Category"])

# Tab 1: Wears by Material (Bar Chart)
with tab1:
    wears_by_material = df_log_long.merge(df_all[['Name', 'Material']], left_on='Item', right_on='Name')
    wears_by_material = wears_by_material['Material'].value_counts().reset_index()
    wears_by_material.columns = ['Material', 'Wears']
    
    fig_wears_material_bar = px.bar(wears_by_material, x='Material', y='Wears', title='Wears by Material (Bar Chart)', labels={'Material': 'Material', 'Wears': 'Number of Wears'})
    st.plotly_chart(fig_wears_material_bar, use_container_width=True)

# Tab 2: Wears by Category (Bar Chart)
with tab2:
    wears_by_category = df_log_long.merge(df_all[['Name', 'Category']], left_on='Item', right_on='Name')
    wears_by_category = wears_by_category['Category'].value_counts().reset_index()
    wears_by_category.columns = ['Category', 'Wears']
    
    fig_wears_category_bar = px.bar(wears_by_category, x='Category', y='Wears', title='Wears by Category (Bar Chart)', labels={'Category': 'Category', 'Wears': 'Number of Wears'})
    st.plotly_chart(fig_wears_category_bar, use_container_width=True)

# Tab 3: Items by Material (Pie Chart)
with tab3:
    items_by_material = df_all['Material'].value_counts().reset_index()
    items_by_material.columns = ['Material', 'Item Count']
    
    fig_items_by_material_pie = px.pie(items_by_material, values='Item Count', names='Material', title='Items by Material (Pie Chart)')
    st.plotly_chart(fig_items_by_material_pie, use_container_width=True)

# Tab 4: Items by Category (Pie Chart)
with tab4:
    items_by_category = df_all['Category'].value_counts().reset_index()
    items_by_category.columns = ['Category', 'Item Count']
    
    fig_items_by_category_pie = px.pie(items_by_category, values='Item Count', names='Category', title='Items by Category (Pie Chart)')
    st.plotly_chart(fig_items_by_category_pie, use_container_width=True)

# Calendar feature to select a day and view the outfit worn on that day
st.write("## View Outfit by Date")

# Date input to select a specific day
selected_date = st.date_input("Select a date to view the outfit", value=pd.to_datetime('today'))

# Convert selected date to the correct format (match with log format, assuming it uses mm/dd/yyyy)
selected_date_str = selected_date.strftime('%m/%d/%Y')

# Check if the selected date exists in the log
df_log['date'] = pd.to_datetime(df_log['date'], format='%m/%d/%Y')  # Ensure correct date format in log
df_selected_day_log = df_log[df_log['date'] == pd.to_datetime(selected_date_str)]

if df_selected_day_log.empty:
    st.write(f"No outfit logged for {selected_date_str}.")
else:
    st.write(f"### Outfit worn on {selected_date_str}")
    
    # Extract outfit details from the log for the selected date
    outfit_row = df_selected_day_log.iloc[0]  # Get the first (and only) row for the selected date
    outfit_items = outfit_row.drop('date').dropna().values  # Drop the date and empty entries

    # Match outfit items with the corresponding details in df_all
    df_worn_items = df_all[df_all['Name'].isin(outfit_items)]
    
    # Display the images of the items worn on the selected day
    display_images_in_grid(df_worn_items)

    # Calculate total cost and cost per wear for the selected items
    total_cost = df_worn_items['Price'].sum()
    st.write(f"**Total cost of the outfit:** ${total_cost:.2f}")

    # Calculate cost per wear for each item
    st.write("### Cost Per Wear of Each Item")
    df_log_long['date'] = pd.to_datetime(df_log_long['date'], format='%m/%d/%Y')
    for _, item in df_worn_items.iterrows():
        # Filter the log to get the number of times this item was worn
        item_wear_count = df_log_long[df_log_long['Item'] == item['Name']].shape[0]
        if item_wear_count == 0:
            item_wear_count = 1  # Avoid division by zero
        cost_per_wear = item['Price'] / item_wear_count
        st.write(f"- **{item['Name']}**: Price: ${item['Price']:.2f}, Worn: {item_wear_count} time(s), Cost per wear: ${cost_per_wear:.2f}")
