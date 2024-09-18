import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import requests
import base64
import plotly.express as px

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
client = gspread.authorize(creds)

spreadsheet = client.open("wardrobe")  
sheet_all = spreadsheet.worksheet("all")  
sheet_log = spreadsheet.worksheet("log")  


def load_all_data():
    data = sheet_all.get_all_records()
    return pd.DataFrame(data)

def load_log_data():
    data = sheet_log.get_all_records()
    return pd.DataFrame(data)

df_all = load_all_data()
df_log = load_log_data()

def convert_to_base64(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return base64.b64encode(response.content).decode()
        else:
            print(f"Failed to load image from {url}: Status Code {response.status_code}")
    except Exception as e:
        print(f"Failed to load image from {url}: {e}")
    return None

def url_to_image_html(url):
    if url:
        base64_image = convert_to_base64(url)
        if base64_image:
            return f'<img src="data:image/jpeg;base64,{base64_image}" width="100" height="auto">'
    return "No image available"

def show_details_in_sidebar(item):
    st.sidebar.write("## Item Details")
    st.sidebar.write(f"**Name:** {item['Name']}")
    st.sidebar.write(f"**Brand:** {item['Brand']}")
    st.sidebar.write(f"**Category:** {item['Category']}")
    st.sidebar.write(f"**Color:** {item['Color']}")
    st.sidebar.write(f"**Material:** {item['Material']}")
    st.sidebar.write(f"**Price:** ${item['Price']:.2f}")

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
                    # Display image directly from the GitHub link
                    st.markdown(url_to_image_html(item['image']), unsafe_allow_html=True)
                    # Clickable title to filter data, using a unique key based on item name
                    if st.button(f"{item['Name']}", key=f"{item_idx}-{item['Name']}"):
                        st.session_state['selected_items'] = [item['Name']]  # Focus on a specific item

# for selected items
if 'selected_items' not in st.session_state:
    st.session_state['selected_items'] = list(df_all['Name'])  # Start with all items selected


# filters and display
st.write("## Roshni's Closet")
col1, col2, col3, col4 = st.columns(4)

#  reset selection to all items 
if st.button("Show All Items"):
    st.session_state['selected_items'] = list(df_all['Name'])

# define the selectboxes and ensure they are initialized
with col1:
    selected_category = st.selectbox("Select Category", options=["All"] + list(df_all["Category"].unique()), index=0)
with col2:
    selected_color = st.selectbox("Select Color", options=["All"] + list(df_all["Color"].unique()), index=0)
with col3:
    selected_brand = st.selectbox("Select Brand", options=["All"] + list(df_all["Brand"].unique()), index=0)
with col4:
    selected_material = st.selectbox("Select Material", options=["All"] + list(df_all["Material"].unique()), index=0)

# filter data based on selection
df_filtered = df_all.copy()

if selected_category and selected_category != "All":
    df_filtered = df_filtered[df_filtered["Category"] == selected_category]

if selected_color and selected_color != "All":
    df_filtered = df_filtered[df_filtered["Color"] == selected_color]

if selected_brand and selected_brand != "All":
    df_filtered = df_filtered[df_filtered["Brand"] == selected_brand]

if selected_material and selected_material != "All":
    df_filtered = df_filtered[df_filtered["Material"] == selected_material]

# All Clothes 
display_images_in_grid(df_filtered)

selected_items = st.session_state['selected_items']

# filter data for selected items
df_selected = df_all[df_all['Name'].isin(selected_items)]

if len(selected_items) == 1:
    selected_item_data = df_selected.iloc[0]
    show_details_in_sidebar(selected_item_data)

def process_log_data(log_df, item_names):
    log_df_long = log_df.melt(id_vars=['date'], var_name='Item Number', value_name='Item').dropna()
    log_df_long['date'] = pd.to_datetime(log_df_long['date'])
    log_df_long = log_df_long[log_df_long['Item'].isin(item_names)]  
    wear_counts = log_df_long.groupby('Item').size().reset_index(name='Wear Count')  
    return log_df_long, wear_counts

df_log_long, wear_counts = process_log_data(df_log, selected_items)

def calculate_cost_per_wear(all_df, wear_counts_df):
    merged = pd.merge(all_df, wear_counts_df, left_on="Name", right_on="Item", how="left").fillna(0)
    merged["Wear Count"] = merged["Wear Count"].replace(0, 1)
    merged["Cost Per Wear"] = merged["Price"] / merged["Wear Count"]
    return merged[["Name", "Price", "Wear Count", "Cost Per Wear"]]

cost_per_wear_df = calculate_cost_per_wear(df_all, wear_counts)

df_wears_filtered = df_log_long.groupby(['date', 'Item']).size().reset_index(name='Wears')
df_wears_filtered['date'] = pd.to_datetime(df_wears_filtered['date'])
df_wears_filtered['Cumulative Wears'] = df_wears_filtered.groupby('Item')['Wears'].cumsum()


tab_total_wears, tab_cost_per_wear, tab_wears_by_month = st.tabs(["Total Wears Over Time", "Cost Per Wear Over Time", "Wears by Month"])

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

with tab_cost_per_wear:
    df_log_long['Wears'] = 1  

    cost_per_wear_over_time = df_log_long.merge(cost_per_wear_df[['Name', 'Price']], left_on='Item', right_on='Name')
    cost_per_wear_over_time['Cumulative Wears'] = cost_per_wear_over_time.groupby('Item')['Wears'].cumsum()

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


st.write("## Overall Wear Statistics")

tab1, tab2, tab3, tab4 = st.tabs(["Wears by Material", "Wears by Category", "Items by Material", "Items by Category"])

with tab1:
    wears_by_material = df_log_long.merge(df_all[['Name', 'Material']], left_on='Item', right_on='Name')
    wears_by_material = wears_by_material['Material'].value_counts().reset_index()
    wears_by_material.columns = ['Material', 'Wears']
    
    fig_wears_material_bar = px.bar(wears_by_material, x='Material', y='Wears', title='Wears by Material (Bar Chart)', labels={'Material': 'Material', 'Wears': 'Number of Wears'})
    st.plotly_chart(fig_wears_material_bar, use_container_width=True)

with tab2:
    wears_by_category = df_log_long.merge(df_all[['Name', 'Category']], left_on='Item', right_on='Name')
    wears_by_category = wears_by_category['Category'].value_counts().reset_index()
    wears_by_category.columns = ['Category', 'Wears']
    
    fig_wears_category_bar = px.bar(wears_by_category, x='Category', y='Wears', title='Wears by Category (Bar Chart)', labels={'Category': 'Category', 'Wears': 'Number of Wears'})
    st.plotly_chart(fig_wears_category_bar, use_container_width=True)

with tab3:
    items_by_material = df_all['Material'].value_counts().reset_index()
    items_by_material.columns = ['Material', 'Item Count']
    
    fig_items_by_material_pie = px.pie(items_by_material, values='Item Count', names='Material', title='Items by Material (Pie Chart)')
    st.plotly_chart(fig_items_by_material_pie, use_container_width=True)

with tab4:
    items_by_category = df_all['Category'].value_counts().reset_index()
    items_by_category.columns = ['Category', 'Item Count']
    
    fig_items_by_category_pie = px.pie(items_by_category, values='Item Count', names='Category', title='Items by Category (Pie Chart)')
    st.plotly_chart(fig_items_by_category_pie, use_container_width=True)

# calendar feature to select a day and view the outfit worn on that day
st.write("## View Outfit by Date")

selected_date = st.date_input("Select a date to view the outfit", value=pd.to_datetime('today'))
selected_date_str = selected_date.strftime('%m/%d/%Y')
df_log['date'] = pd.to_datetime(df_log['date'], format='%m/%d/%Y')  # Ensure correct date format in log
df_selected_day_log = df_log[df_log['date'] == pd.to_datetime(selected_date_str)]

if df_selected_day_log.empty:
    st.write(f"No outfit logged for {selected_date_str}.")
else:
    st.write(f"### Outfit worn on {selected_date_str}")
    
    outfit_row = df_selected_day_log.iloc[0]  
    outfit_items = outfit_row.drop('date').dropna().values  

    df_worn_items = df_all[df_all['Name'].isin(outfit_items)]
    
    display_images_in_grid(df_worn_items)

    total_cost = df_worn_items['Price'].sum()
    st.write(f"**Total cost of the outfit:** ${total_cost:.2f}")

    st.write("### Cost Per Wear of Each Item")
    df_log_long['date'] = pd.to_datetime(df_log_long['date'], format='%m/%d/%Y')
    for _, item in df_worn_items.iterrows():
        item_wear_count = df_log_long[df_log_long['Item'] == item['Name']].shape[0]
        if item_wear_count == 0:
            item_wear_count = 1  
        cost_per_wear = item['Price'] / item_wear_count
        st.write(f"- **{item['Name']}**: Price: ${item['Price']:.2f}, Worn: {item_wear_count} time(s), Cost per wear: ${cost_per_wear:.2f}")
