# -*- coding: utf-8 -*-
"""
Dieses Skript liest Seriendaten aus CSV-Dateien, ruft ergänzende
Informationen von Wikipedia und The Movie Database (TMDB) ab und
indexiert alles mit Tantivy, um eine durchsuchbare Volltext-Indizestruktur
zu erstellen.

Hauptschritte:
1) Schema für den Tantivy-Index definieren.
2) Index-Verzeichnis erstellen und Writer initialisieren.
3) Wikipedia‑Client mit benutzerdefiniertem User‑Agent aufsetzen.
4) CSV‑Daten (Serien + IMDb) einlesen und mergen.
5) Für jede Serie: Wikipedia-Seite laden, TMDB-Daten per API ergänzen,
   Dokument zusammenstellen und in den Index schreiben.
6) Änderungen committen und Merge-Threads abwarten.
"""

import pandas as pd
import wikipediaapi
import re
from urllib.parse import urlparse, unquote
from tantivy import Facet, SchemaBuilder, Index, Document
import pathlib
import json
import requests
import os
from itertools import islice
from dotenv import load_dotenv


# Basis-URLs für TMDB-Requests
TMDB_API = "https://api.themoviedb.org/3/find/"
TMDB_TRAILER_API = "https://api.themoviedb.org/3/tv/"
SOURCE = "?external_source=imdb_id"  # Parameter, um via IMDb-ID zu suchen

#Umgebungsvariablen laden
load_dotenv()

# HTTP-Header inkl. Bearer-Token für TMDB (siehe Sicherheitshinweis oben)
headers = {
    "accept": "application/json",
    "Authorization": os.getenv('TMDB_API_KEY')
}

# === 1) Schema für den Index definieren ===
# Textfelder
schema_builder = SchemaBuilder()
schema_builder.add_text_field("wikidata", stored=True)
schema_builder.add_text_field("url", stored=True)
schema_builder.add_text_field("title", stored=True, tokenizer_name='en_stem')
schema_builder.add_text_field("description", stored=True, tokenizer_name='en_stem')  # Mehrwertiges Textfeld
schema_builder.add_text_field("image", stored=True)
schema_builder.add_text_field("locations", stored=True)
schema_builder.add_text_field("countries", stored=True)
schema_builder.add_text_field("genres", stored=True)
schema_builder.add_text_field("tmdb_overview", stored=True, tokenizer_name='en_stem')
schema_builder.add_text_field("tmdb_poster_path", stored=True)
schema_builder.add_text_field("trailer", stored=True)

# Integer-Felder
schema_builder.add_integer_field("id", stored=True, indexed=True)
schema_builder.add_integer_field("follower", stored=True, fast=True)
schema_builder.add_integer_field("score", stored=True, fast=True)
schema_builder.add_integer_field("start", stored=True, fast=True)
schema_builder.add_integer_field("tmdb_genre_ids", stored=True, indexed=True)
schema_builder.add_integer_field("tmdb_vote_count", stored=True, fast=True)

# Float-Felder
schema_builder.add_float_field("tmdb_popularity", stored=True, fast=True)
schema_builder.add_float_field("tmdb_vote_average", stored=True, fast=True)

# Facet-Felder (für hierarchische Filter/Navigation)
schema_builder.add_facet_field("facet_locations")
schema_builder.add_facet_field("facet_countries")
schema_builder.add_facet_field("facet_genres")

# Schema finalisieren
schema = schema_builder.build()

# === 2) Index anlegen/öffnen ===
index_path = "neu"  # Relativer Pfad für das Index-Verzeichnis
if not os.path.exists(index_path):
    os.makedirs(index_path)
    print(f"Der {index_path}-Ordner wurde angelegt.")
else:
    print(f"Ordner {index_path} existiert bereits.")

index_path = pathlib.Path(index_path)
index = Index(schema, path=str(index_path))
writer = index.writer()  # Writer für Batch-Schreibvorgänge

# === 3) Wikipedia-Client mit Session und User-Agent ===
custom_user_agent = "MyWikipediaBot/1.0 (https://example.com; myemail@example.com)"
session = requests.Session()
session.headers.update({'User-Agent': custom_user_agent})

# Wikipedia-API-Objekt; Session explizit zuweisen, um Rate Limits zu respektieren
wiki = wikipediaapi.Wikipedia(language='en', user_agent=custom_user_agent)
wiki.session = session

# === 4) CSVs einlesen ===
file_path = 'series.csv'  # Pfad zur Serienliste (muss existieren)
imdb_path = "imdb.csv"   # Pfad zur IMDb-Tabelle (muss existieren)

data_incomplete = pd.read_csv(file_path)
imdb = pd.read_csv(imdb_path)

# DataFrames anhand der Spalte 'series' zusammenführen (inner join)
data = pd.merge(data_incomplete, imdb, on='series', how='inner')
df = pd.DataFrame(data)  # optional: falls weitere Pandas-Operationen geplant sind

# === 5) Dokumente aufbauen und in den Index schreiben ===
# islice(..., 10) beschränkt auf die ersten 10 Einträge – bei Bedarf anpassen/entfernen
for index, row in islice(data.iterrows(), 10):
    # Wikipedia-Titel aus der URL extrahieren und decodieren
    path = urlparse(row["wikipediaPage"]).path
    title_encoded = path.split("/")[-1]
    title = unquote(title_encoded).replace("_", " ")
    # Klammern (inkl. Inhalt) entfernen, um robustere Titel zu erhalten
    clean_title = re.sub(r"\s*\(.*?\)", "", title).strip()

    # Wikipedia-Seite abrufen
    page = wiki.page(title)
    if page.exists():
        print(index)
        try:
            # Neues Tantivy-Dokument
            doc = Document()

            # Pflicht-/Basisfelder
            doc.add_integer("id", index)
            doc.add_text("wikidata", row["series"])  # Serien-ID/Name aus den CSVs
            doc.add_text("url", row["wikipediaPage"])  # Wikipedia-URL
            doc.add_text("title", row["seriesLabel"])  # Anzeigename/Titel
            doc.add_text("description", page.summary)   # Wikipedia-Zusammenfassung

            # Optionale numerische Felder, nur wenn Werte vorhanden sind
            if pd.notna(row["follower"]):
                doc.add_integer("follower", int(row["follower"]))
            if pd.notna(row["score"]):
                doc.add_integer("score", int(row["score"]))

            # Optionales Bild (z. B. aus Wikidata/CSV)
            if pd.notna(row["image"]) and row["image"].strip() != "":
                doc.add_text("image", row["image"])

            # Startjahr/Startzeit (als Integer gespeichert)
            doc.add_integer("start", int(row["startTime"]))

            # Mehrwertige Felder + Facets für Filterung (Orte, Länder, Genres)
            if pd.notna(row["locations"]):
                for location in str(row["locations"]).split(", "):
                    doc.add_text("locations", location)
                    doc.add_facet("facet_locations", Facet.from_string(f"/{location.strip().strip('/')}"))

            if pd.notna(row["countries"]):
                for country in str(row["countries"]).split(", "):
                    doc.add_text("countries", country)
                    doc.add_facet("facet_countries", Facet.from_string(f"/{country.strip().strip('/')}"))

            if pd.notna(row["genres"]):
                for genre in str(row["genres"]).split(", "):
                    doc.add_text("genres", genre)
                    doc.add_facet("facet_genres", Facet.from_string(f"/{genre.strip().strip('/')}"))

            # === TMDB-Abfragen (auf Basis der IMDb-ID) ===
            try:
                response = requests.get(TMDB_API + row["imdb"] + SOURCE, headers=headers)
                tmdb_json = json.loads(response.text)

                # Prüfen, ob TV-Ergebnisse vorhanden sind (wir nehmen das erste)
                if tmdb_json.get("tv_results"):
                    tmdb = tmdb_json["tv_results"][0]

                    # Optional: Inhaltsangabe/Overview
                    if tmdb.get("overview"):
                        tmdb_overview = tmdb.get("overview")
                        doc.add_text("tmdb_overview", tmdb_overview)

                    # Optional: Posterpfad
                    if tmdb.get("poster_path"):
                        tmdb_poster_path = tmdb.get("poster_path")
                        doc.add_text("tmdb_poster_path", tmdb_poster_path)

                    # Optional: Genre-IDs (mehrwertig als Integers)
                    if tmdb.get("genre_ids"):
                        for genre in tmdb.get("genre_ids"):
                            doc.add_integer("tmdb_genre_ids", genre)

                    # Popularität & Bewertungen (Floats/Integers)
                    if tmdb.get("popularity"):
                        tmdb_popularity = tmdb.get("popularity")
                        doc.add_float("tmdb_popularity", tmdb_popularity)
                    if tmdb.get("vote_average"):
                        tmdb_vote_average = tmdb.get("vote_average")
                        doc.add_float("tmdb_vote_average", tmdb_vote_average)
                    if tmdb.get("vote_count"):
                        tmdb_vote_count = tmdb.get("vote_count")
                        doc.add_integer("tmdb_vote_count", tmdb_vote_count)

                    # Trailer-Key über zusätzliche TMDB-API (Videos) ermitteln

                else:
                    print("No TV results found.")
            except Exception as e:
                # Fehler in der TMDB-Abfrage protokollieren, Indexierung dennoch fortsetzen
                print("TMDB Error")

            # Fertiges Dokument in den Index schreiben
            writer.add_document(doc)

        except Exception as e:
            # Falls etwas schiefgeht: überspringen, aber Fehlermeldung ausgeben
            print(f"{e} Something went wrong. Skipping series")

    else:
        # Wikipedia-Seite existiert nicht – Eintrag überspringen
        print(str(index) + " Page does not exist.")

# === 6) Index-Änderungen finalisieren ===
writer.commit()                 # Schreibvorgänge bestätigen
writer.wait_merging_threads()   # Hintergrund-Mergeprozesse abwarten
