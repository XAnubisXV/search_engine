import pandas as pd
import wikipediaapi
import re
from urllib.parse import urlparse, unquote, quote
from tantivy import Facet, SchemaBuilder, Index, Document
import json
import requests
import os
from dotenv import load_dotenv
import trailer
import random
import time

# --- CONFIG ---
TMDB_FIND_API = "https://api.themoviedb.org/3/find/"
TMDB_SEARCH_API = "https://api.themoviedb.org/3/search/tv"
TMDB_DETAILS_API = "https://api.themoviedb.org/3/tv/"
SOURCE_PARAMS = "?external_source=imdb_id&language=de-DE"
SEARCH_PARAMS = "&language=de-DE"
INDEX_PATH = "serien_db"
load_dotenv()

# API KEY
api_key = os.getenv('TMDB_API_KEY')
headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {api_key}" if api_key and not api_key.startswith("Bearer") else api_key
}

# 1. SCHEMA
schema_builder = SchemaBuilder()
schema_builder.add_text_field("wikidata", stored=True)
schema_builder.add_text_field("url", stored=True)
schema_builder.add_text_field("title", stored=True, tokenizer_name='de_stem')
schema_builder.add_text_field("description", stored=True, tokenizer_name='de_stem')
schema_builder.add_text_field("image", stored=True)

# Filter Felder
schema_builder.add_text_field("genres", stored=True)
schema_builder.add_text_field("providers", stored=True)
schema_builder.add_text_field("countries", stored=True)

# TMDB
schema_builder.add_text_field("tmdb_overview", stored=True, tokenizer_name='de_stem')
schema_builder.add_text_field("tmdb_poster_path", stored=True)
schema_builder.add_text_field("trailer", stored=True)
schema_builder.add_text_field("actors", stored=True, tokenizer_name='en_stem')
schema_builder.add_text_field("writers", stored=True, tokenizer_name='en_stem')

# Zahlen
schema_builder.add_integer_field("id", stored=True, indexed=True)
schema_builder.add_integer_field("score", stored=True, fast=True)
schema_builder.add_integer_field("start", stored=True, fast=True)
schema_builder.add_integer_field("tmdb_vote_count", stored=True, fast=True)
schema_builder.add_integer_field("is_based_on_book", stored=True, indexed=True)
schema_builder.add_integer_field("is_true_story", stored=True, indexed=True)
schema_builder.add_float_field("tmdb_popularity", stored=True, fast=True)
schema_builder.add_float_field("tmdb_vote_average", stored=True, fast=True)

# Facetten
schema_builder.add_facet_field("facet_genres")
schema_builder.add_facet_field("facet_providers")

schema = schema_builder.build()

if not os.path.exists(INDEX_PATH):
    os.makedirs(INDEX_PATH)

index = Index(schema, path=str(INDEX_PATH))
writer = index.writer()

# WIKI
custom_user_agent = "MySeriesBot/1.0 (test@example.com)"
session = requests.Session()
session.headers.update({'User-Agent': custom_user_agent})
wiki = wikipediaapi.Wikipedia(language='de', user_agent=custom_user_agent)
wiki.session = session

GENRE_MAP = {
    "Comedy": "Komödie", "Science Fiction": "Science-Fiction", "Sci-Fi": "Science-Fiction",
    "Action": "Action", "Drama": "Drama", "Crime": "Krimi", "Adventure": "Abenteuer",
    "Thriller": "Thriller", "Animation": "Animation", "Family": "Familie", "Mystery": "Mystery",
    "Documentary": "Dokumentation", "Romance": "Romantik", "Fantasy": "Fantasy",
    "War": "Krieg", "Western": "Western", "Horror": "Horror", "Music": "Musik", "Reality": "Reality-TV"
}

# DATEN LADEN
print("Lade CSV Dateien...")
try:
    s = pd.read_csv('series.csv')
    i = pd.read_csv("imdb.csv")
    data = pd.merge(s, i, on='series', how='inner')
except:
    try:
        s = pd.read_csv('series.csv', encoding='latin1', on_bad_lines='skip', sep=None, engine='python')
        i = pd.read_csv("imdb.csv", encoding='latin1', on_bad_lines='skip', sep=None, engine='python')
        data = pd.merge(s, i, on='series', how='inner')
    except Exception as e:
        print(f"Fehler: {e}")
        exit()

print(f"Daten geladen. {len(data)} Zeilen.")


def check_keywords(text, keywords):
    if not text: return 0
    text = text.lower()
    for k in keywords:
        if k in text: return 1
    return 0


POSSIBLE_PROVIDERS = ["Netflix", "Amazon Prime", "Disney+", "Hulu", "Apple TV+", "Sky/Wow", "RTL+"]

# --- HIER WURDE DAS LIMIT ENTFERNT ---
print(f"Starte Indexierung von ALLEN {len(data)} Serien...")
count = 0

# HIER WURDE islice() ENTFERNT, DAMIT ALLES DURCHLÄUFT
for index, row in data.iterrows():
    try:
        path = urlparse(row["wikipediaPage"]).path
        title = unquote(path.split("/")[-1]).replace("_", " ")
        page = wiki.page(title)
        description = page.summary if page.exists() else ""

        doc = Document()
        doc.add_integer("id", index)
        doc.add_text("wikidata", row["series"])
        doc.add_text("url", row["wikipediaPage"])
        doc.add_text("title", row["seriesLabel"])
        doc.add_text("description", description)

        if pd.notna(row.get("image")): doc.add_text("image", str(row["image"]))
        if pd.notna(row.get("startTime")): doc.add_integer("start", int(row["startTime"]))
        if pd.notna(row.get("score")): doc.add_integer("score", int(row["score"]))

        # Genre
        raw_genre = None
        for col in ["genres", "genre", "Genre", "genreLabel"]:
            if col in row and pd.notna(row[col]):
                raw_genre = row[col]
                break

        if raw_genre:
            for g in str(raw_genre).split(","):
                g_clean = g.strip()
                g_german = GENRE_MAP.get(g_clean, g_clean)
                doc.add_text("genres", g_german)
                doc.add_facet("facet_genres", Facet.from_string(f"/{g_german.replace('/', ' ')}"))

        # Plattform
        my_providers = random.sample(POSSIBLE_PROVIDERS, k=random.randint(1, 3))
        for prov in my_providers:
            doc.add_text("providers", prov)
            doc.add_facet("facet_providers", Facet.from_string(f"/{prov}"))

        # TMDB
        try:
            tmdb_id = None
            tv_result = None
            if pd.notna(row.get("imdb")):
                resp = requests.get(TMDB_FIND_API + str(row["imdb"]) + SOURCE_PARAMS, headers=headers)
                data_json = resp.json()
                if data_json.get("tv_results"):
                    tv_result = data_json["tv_results"][0]
                    tmdb_id = tv_result.get("id")

            if not tmdb_id:
                search_url = f"{TMDB_SEARCH_API}?query={quote(row['seriesLabel'])}{SEARCH_PARAMS}"
                resp_search = requests.get(search_url, headers=headers)
                search_json = resp_search.json()
                if search_json.get("results"):
                    tv_result = search_json["results"][0]
                    tmdb_id = tv_result.get("id")

            if tv_result:
                doc.add_text("tmdb_overview", tv_result.get("overview", ""))
                poster = tv_result.get("poster_path")
                if poster: doc.add_text("tmdb_poster_path", poster)
                doc.add_float("tmdb_popularity", tv_result.get("popularity", 0.0))
                doc.add_float("tmdb_vote_average", tv_result.get("vote_average", 0.0))
                doc.add_integer("tmdb_vote_count", tv_result.get("vote_count", 0))

                full_text = (description + " " + tv_result.get("overview", "")).lower()
                doc.add_integer("is_based_on_book",
                                check_keywords(full_text, ["buch", "roman", "novel", "book", "basiert auf"]))
                doc.add_integer("is_true_story", check_keywords(full_text,
                                                                ["wahre begebenheit", "true story", "biografie",
                                                                 "biography"]))

                if tmdb_id:
                    time.sleep(0.05)
                    c = requests.get(f"{TMDB_DETAILS_API}{tmdb_id}/credits", headers=headers).json()
                    for cast in c.get('cast', [])[:5]:
                        doc.add_text("actors", cast['name'])
                    v = requests.get(f"{TMDB_DETAILS_API}{tmdb_id}/videos?language=de-DE", headers=headers)
                    res_v = v.json()
                    if not res_v.get('results'):
                        v = requests.get(f"{TMDB_DETAILS_API}{tmdb_id}/videos", headers=headers)
                    key = trailer.get_key(v.text)
                    if isinstance(key, str):
                        doc.add_text("trailer", key)
        except:
            pass

        writer.add_document(doc)
        count += 1
        if count % 20 == 0: print(f"{count} Serien verarbeitet...")

    except Exception as e:
        print(f"Fehler Zeile {index}: {e}")

writer.commit()
writer.wait_merging_threads()
print(f"FERTIG! {count} Serien indexiert.")