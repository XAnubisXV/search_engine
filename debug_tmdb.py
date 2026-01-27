import os
import requests
from dotenv import load_dotenv

# 1. Versuche, die .env Datei zu laden
print("--- DIAGNOSE START ---")
load_dotenv()

api_key = os.getenv('TMDB_API_KEY')

# 2. Prüfen, ob der Key überhaupt gefunden wurde
if not api_key:
    print("FEHLER: Kein API Key gefunden!")
    print("Mögliche Ursachen:")
    print(" - Die Datei heißt '.env.txt' statt '.env'")
    print(" - Die Datei liegt im falschen Ordner")
    print(" - Die Datei ist leer")
else:
    print(f"OK: Key gefunden (Startet mit: {api_key[:4]}...)")

    # 3. Prüfen, ob der Key funktioniert (Test-Anfrage an TMDB)
    url = f"https://api.themoviedb.org/3/authentication/token/new?api_key={api_key}"
    response = requests.get(url)

    if response.status_code == 200:
        print("ERFOLG: Der Key ist gültig! Verbindung zu TMDB steht.")
    elif response.status_code == 401:
        print("FEHLER: Der Key ist ungültig (falsch kopiert?).")
    else:
        print(f"FEHLER: Verbindungsproblem (Code: {response.status_code})")

print("--- DIAGNOSE ENDE ---")