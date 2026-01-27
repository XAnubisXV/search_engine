import pandas as pd
import wikipediaapi
import re
from urllib.parse import urlparse, unquote
from tantivy import Facet, SchemaBuilder, Index, Document
import json
import requests
import os
from itertools import islice
from dotenv import load_dotenv
import trailer

# Config
TMDB_API = "https://api.themoviedb.org/3/find/"
TMDB_DETAILS_API = "https://api.themoviedb.org/3/tv/"
SOURCE = "?external_source=imdb_id"
load_dotenv()

api_key = os.getenv('TMDB_API_KEY')
if not api_key:
    print("ACHTUNG: Kein TMDB_API_KEY gefunden! Bitte .env Datei prüfen.")

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {api_key}" if api_key and not api_key.startswith("Bearer") else api_key
}

# 1. Schema
schema_builder = SchemaBuilder()
schema_builder.add_text_field("wikidata", stored=True)
schema_builder.add_text_field("url", stored=True)
schema_builder.add_text_field("title", stored=True, tokenizer_name='en_stem')
schema_builder.add_text_field("description", stored=True, tokenizer_name='en_stem')
schema_builder.add_text_field("image", stored=True)
schema_builder.add_text_field("locations", stored=True)
schema_builder.add_text_field("countries", stored=True)
schema_builder.add_text_field("genres", stored=True)
schema_builder.add_text_field("tmdb_overview", stored=True, tokenizer_name='en_stem')
schema_builder.add_text_field("tmdb_poster_path", stored=True)
schema_builder.add_text_field("trailer", stored=True)
schema_builder.add_text_field("actors", stored=True, tokenizer_name='en_stem')
schema_builder.add_text_field("writers", stored=True, tokenizer_name='en_stem')
schema_builder.add_integer_field("id", stored=True, indexed=True)
schema_builder.add_integer_field("follower", stored=True, fast=True)
schema_builder.add_integer_field("score", stored=True, fast=True)
schema_builder.add_integer_field("start", stored=True, fast=True)
schema_builder.add_integer_field("tmdb_genre_ids", stored=True, indexed=True)
schema_builder.add_integer_field("tmdb_vote_count", stored=True, fast=True)
schema_builder.add_integer_field("is_based_on_book", stored=True, indexed=True)
schema_builder.add_integer_field("is_true_story", stored=True, indexed=True)
schema_builder.add_float_field("tmdb_popularity", stored=True, fast=True)
schema_builder.add_float_field("tmdb_vote_average", stored=True, fast=True)
schema_builder.add_facet_field("facet_locations")
schema_builder.add_facet_field("facet_countries")
schema_builder.add_facet_field("facet_genres")

schema = schema_builder.build()

# 2. Index Ordner
index_path = "serien_300"
if not os.path.exists(index_path):
    os.makedirs(index_path)

index = Index(schema, path=str(index_path))
writer = index.writer()

# 3. Wikipedia
custom_user_agent = "MyWikipediaBot/1.0 (test@example.com)"
session = requests.Session()
session.headers.update({'User-Agent': custom_user_agent})
wiki = wikipediaapi.Wikipedia(language='en', user_agent=custom_user_agent)
wiki.session = session

# 4. Daten laden
print("Lade CSV Dateien...")
try:
    if not os.path.exists('series.csv') or not os.path.exists('imdb.csv'):
        print("FEHLER: series.csv oder imdb.csv nicht gefunden!")
        exit()

    df1 = pd.read_csv('series.csv')
    df2 = pd.read_csv('imdb.csv')
    data = pd.merge(df1, df2, on='series', how='inner')
    print(f"CSV geladen. Anzahl Zeilen: {len(data)}")
except Exception as e:
    print(f"Kritischer Fehler beim Laden der CSVs: {e}")
    exit()


def check_keywords(text, keywords):
    if not text: return 0
    text = text.lower()
    for k in keywords:
        if k in text: return 1
    return 0


print("Starte Indexierung (Max 300 Einträge)...")
count = 0

for index, row in islice(data.iterrows(), 300):
    try:
        # Titel extrahieren
        path = urlparse(row["wikipediaPage"]).path
        title = unquote(path.split("/")[-1]).replace("_", " ")

        # Wiki Check (nur wenn Seite existiert)
        page = wiki.page(title)
        if not page.exists():
            print(f"Skipping {title} (Wiki Page not found)")
            continue

        doc = Document()
        doc.add_integer("id", index)
        doc.add_text("wikidata", row["series"])
        doc.add_text("url", row["wikipediaPage"])
        doc.add_text("title", row["seriesLabel"])
        doc.add_text("description", page.summary)

        if pd.notna(row.get("image")): doc.add_text("image", str(row["image"]))
        if pd.notna(row.get("startTime")): doc.add_integer("start", int(row["startTime"]))
        if pd.notna(row.get("score")): doc.add_integer("score", int(row["score"]))

        if pd.notna(row.get("locations")):
            for loc in str(row["locations"]).split(", "):
                doc.add_text("locations", loc)
                doc.add_facet("facet_locations", Facet.from_string(f"/{loc.strip().strip('/')}"))

        if pd.notna(row.get("genres")):
            for g in str(row["genres"]).split(", "):
                doc.add_text("genres", g)
                doc.add_facet("facet_genres", Facet.from_string(f"/{g.strip().strip('/')}"))

        # TMDB
        try:
            resp = requests.get(TMDB_API + str(row["imdb"]) + SOURCE, headers=headers)
            tmdb_data = json.loads(resp.text)

            if tmdb_data.get("tv_results"):
                tv = tmdb_data["tv_results"][0]
                tmdb_id = tv.get("id")

                doc.add_text("tmdb_overview", tv.get("overview", ""))
                doc.add_text("tmdb_poster_path", tv.get("poster_path", ""))
                doc.add_float("tmdb_popularity", tv.get("popularity", 0.0))
                doc.add_float("tmdb_vote_average", tv.get("vote_average", 0.0))

                # Filter Keywords
                full_text = (page.summary + " " + tv.get("overview", "")).lower()
                doc.add_integer("is_based_on_book",
                                check_keywords(full_text, ["based on the novel", "based on the book", "adaptation"]))
                doc.add_integer("is_true_story", check_keywords(full_text, ["true story", "real events", "biography"]))

                # Actors
                if tmdb_id:
                    c_resp = requests.get(f"{TMDB_DETAILS_API}{tmdb_id}/credits", headers=headers)
                    if c_resp.status_code == 200:
                        credits = c_resp.json()
                        for c in credits.get('cast', [])[:5]:
                            doc.add_text("actors", c['name'])

                    # Trailer
                    v_resp = requests.get(f"{TMDB_DETAILS_API}{tmdb_id}/videos", headers=headers)
                    if v_resp.status_code == 200:
                        key = trailer.get_key(v_resp.text)
                        if isinstance(key, str):
                            doc.add_text("trailer", key)

        except Exception as api_err:
            print(f"API Warning ({title}): {api_err}")

        writer.add_document(doc)
        count += 1
        if count % 10 == 0:
            print(f"{count} Serien verarbeitet...")

    except Exception as e:
        print(f"Fehler bei Zeile {index}: {e}")

# WICHTIG: Commit Bestätigung
print(f"Committing {count} Dokumente in den Index...")
writer.commit()
writer.wait_merging_threads()
print(f"FERTIG! Index enthält jetzt {count} durchsuchbare Serien.")