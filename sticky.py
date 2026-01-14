import streamlit as st

# Seiten festlegen
page1 = st.Page("seiten/seite1.py", title="Home")
page2 = st.Page("seiten/seite2.py", title="Test")

# Navigationsstruktur festlegen
pages_config = {
    "": [page1, page2]
    #"": [page1],
    #"Aufklappmenü": [page2],
}

# CSS einlesen
with open("page_styles.html", "r") as f:
    css = f.read()
st.set_page_config(layout="wide")
st.markdown(css, unsafe_allow_html=True)

# Navigationsstruktur erstellen
navigation = st.navigation(pages_config, position="top")
navigation.run()