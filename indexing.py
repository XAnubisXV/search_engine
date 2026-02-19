import pandas as pd
import wikipediaapi
import re
from urllib.parse import urlparse, unquote, quote
from tantivy import Facet, SchemaBuilder, Index, Document
from itertools import islice
import json
import requests
import os
from dotenv import load_dotenv
import trailer
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
    "War": "Krieg", "Western": "Western", "Horror": "Horror", "Music": "Musik", "Reality": "Reality-TV",
    "History": "Historisch", "Talk": "Stand-Up"
}

# Mapping: TMDB Provider-Namen auf unsere einheitlichen Namen
PROVIDER_NAME_MAP = {
    "Netflix": "Netflix",
    "Netflix basic with Ads": "Netflix",
    "Amazon Prime Video": "Amazon Prime",
    "Amazon Video": "Amazon Prime",
    "Disney Plus": "Disney+",
    "Disney+": "Disney+",
    "Paramount Plus": "Paramount+",
    "Paramount+ Amazon Channel": "Paramount+",
    "Paramount Plus Apple TV Channel": "Paramount+",
    "HBO Max": "HBO Max",
    "Max": "HBO Max",
    "Max Amazon Channel": "HBO Max",
    "Apple TV Plus": "Apple TV+",
    "Apple TV+": "Apple TV+",
    "WOW": "WOW",
    "Sky Go": "WOW",
    "Sky Ticket": "WOW",
    "Joyn": "Joyn",
    "Joyn Plus": "Joyn",
    "RTL+": "RTL+",
    "RTL Plus": "RTL+",
    "Amazon Freevee": "Amazon Freevee",
    "Freevee": "Amazon Freevee",
    "Crunchyroll": "Crunchyroll",
    "MagentaTV": "MagentaTV",
    "ARD Mediathek": "ARD Mediathek",
    "ZDF": "ZDF Mediathek",
    "ZDF Mediathek": "ZDF Mediathek",
    "Hulu": "Hulu",
}


def get_watch_providers_de(tmdb_id):
    """Holt die echten Streaming-Plattformen fuer Deutschland von der TMDB API."""
    providers_found = set()
    try:
        url = f"{TMDB_DETAILS_API}{tmdb_id}/watch/providers"
        resp = requests.get(url, headers=headers)
        data_wp = resp.json()

        de_data = data_wp.get("results", {}).get("DE", {})

        # flatrate = Streaming-Abo (Netflix, Disney+ etc.)
        for p in de_data.get("flatrate", []):
            name = p.get("provider_name", "")
            mapped = PROVIDER_NAME_MAP.get(name)
            if mapped:
                providers_found.add(mapped)

        # ads = Kostenlos mit Werbung (Freevee, Joyn etc.)
        for p in de_data.get("ads", []):
            name = p.get("provider_name", "")
            mapped = PROVIDER_NAME_MAP.get(name)
            if mapped:
                providers_found.add(mapped)

        # free = Komplett kostenlos (ARD, ZDF etc.)
        for p in de_data.get("free", []):
            name = p.get("provider_name", "")
            mapped = PROVIDER_NAME_MAP.get(name)
            if mapped:
                providers_found.add(mapped)

    except Exception as e:
        print(f"  Watch Providers Fehler: {e}")

    return list(providers_found)


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


# --- LIMIT: Maximale Anzahl der zu indexierenden Serien ---
LIMIT = 7000
print(f"Starte Indexierung von {LIMIT} Serien...")
count = 0

for idx, row in islice(data.iterrows(), LIMIT):
    try:
        path = urlparse(row["wikipediaPage"]).path
        title = unquote(path.split("/")[-1]).replace("_", " ")
        page = wiki.page(title)
        description = page.summary if page.exists() else ""

        doc = Document()
        doc.add_integer("id", idx)
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

                # --- ECHTE PLATTFORMEN VON TMDB HOLEN ---
                if tmdb_id:
                    time.sleep(0.05)

                    # Watch Providers fuer Deutschland
                    real_providers = get_watch_providers_de(tmdb_id)
                    for prov in real_providers:
                        doc.add_text("providers", prov)
                        doc.add_facet("facet_providers", Facet.from_string(f"/{prov}"))

                    if real_providers:
                        print(f"  [{row['seriesLabel']}] Plattformen: {', '.join(real_providers)}")

                    # Credits (Schauspieler)
                    c = requests.get(f"{TMDB_DETAILS_API}{tmdb_id}/credits", headers=headers).json()
                    for cast in c.get('cast', [])[:5]:
                        doc.add_text("actors", cast['name'])

                    # Trailer
                    v = requests.get(f"{TMDB_DETAILS_API}{tmdb_id}/videos?language=de-DE", headers=headers)
                    res_v = v.json()
                    if not res_v.get('results'):
                        v = requests.get(f"{TMDB_DETAILS_API}{tmdb_id}/videos", headers=headers)
                    key = trailer.get_key(v.text)
                    if isinstance(key, str):
                        doc.add_text("trailer", key)
        except Exception as e:
            print(f"  TMDB Fehler fuer {row['seriesLabel']}: {e}")

        writer.add_document(doc)
        count += 1
        if count % 20 == 0: print(f"{count} Serien verarbeitet...")

    except Exception as e:
        print(f"Fehler Zeile {idx}: {e}")

writer.commit()
writer.wait_merging_threads()
print(f"FERTIG! {count} Serien indexiert.")