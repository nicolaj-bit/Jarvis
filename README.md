# Jarvis

En stemmestyret assistent, der kører lokalt på din Windows-PC. Det her er
**fase 1**: tryk-for-tale, dansk tale til tekst, Claude med værktøjer og
oplæsning af svaret.

```
Hold Ctrl+Alt+J  →  optagelse  →  faster-whisper (lokalt)  →  Claude + værktøjer  →  oplæsning
```

Jarvis lever som et lille rundt ikon i proceslinjen. Farven viser, hvad den laver:

| Farve  | Tilstand                              |
|--------|---------------------------------------|
| Grå    | Starter op                            |
| Blå    | Klar                                  |
| Rød    | Lytter (du holder tasten nede)        |
| Gul    | Tænker                                |
| Grøn   | Taler                                 |
| Lilla  | Venter på dit ja eller nej            |

Højreklik på ikonet for at åbne logfilen eller afslutte.

---

## Installation

Du skal bruge **Python 3.11 eller nyere** (3.12 anbefales) fra
[python.org](https://www.python.org/downloads/windows/). Sæt flueben i
«Add python.exe to PATH» under installationen.

Åbn PowerShell i projektmappen og kør:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Får du en fejl om «running scripts is disabled», så kør først
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` og prøv igen.

### Dansk stemme til oplæsningen

Den lokale oplæsning bruger Windows' egne stemmer. For at få dansk:
**Indstillinger → Tid og sprog → Tale → Tilføj stemmer → Dansk**.
Uden en dansk stemme læser Jarvis op med den engelske standardstemme.

---

## Opsætning

### 1. `.env` — hemmelige nøgler

Kopiér `.env.example` til `.env` og udfyld:

```ini
ANTHROPIC_API_KEY=sk-ant-...      # påkrævet, fra console.anthropic.com
ELEVENLABS_API_KEY=               # kun hvis du skifter til ElevenLabs
```

`.env` står i `.gitignore` og kommer aldrig i repoet.

### 2. `config.toml` — indstillinger

Første gang Jarvis starter, kopierer den `config.example.toml` til
`config.toml`. Den fil er din egen og kommer heller ikke i repoet. De
vigtigste punkter:

```toml
[hotkey]
push_to_talk = "ctrl+alt+j"

[stt]
model = "large-v3-turbo"   # skift model her
language = "da"

[brain]
model = "claude-opus-5-5"
effort = "medium"           # low = hurtigere svar, high = mere grundig

[tts]
engine = "local"            # eller "elevenlabs"

[tts.elevenlabs]
voice_id = ""               # stemme-id fra din ElevenLabs-konto

[files]
# Filværktøjerne må KUN arbejde i disse mapper. Alt andet afvises.
allowed_dirs = [
    'C:\Users\nicolaj\Documents\Jarvis',
]

[programs]
# Programmer Jarvis må starte, efter navn.
notesblok = "notepad.exe"
lommeregner = "calc.exe"
```

**Ret `allowed_dirs`, før du starter** — standardstien er et eksempel.
Mappen skal findes.

---

## Start

```powershell
.\.venv\Scripts\Activate.ps1
python -m jarvis
```

Første start henter talemodellen (ca. 1,6 GB for `large-v3-turbo`). Det
tager et par minutter én gang. Når ikonet bliver blåt, holder du
**Ctrl+Alt+J** nede, taler og slipper.

Vil du starte uden konsolvindue, så brug `pythonw -m jarvis`.

### Testkommandoer

```powershell
python -m jarvis --test-stt    # optag og mål hvor hurtig tale til tekst er
python -m jarvis --test-tts    # hør oplæsningen
python -m jarvis --console     # skriv til Jarvis i stedet for at tale
```

`--console` er nyttig til at teste Claude og værktøjerne uden mikrofon.

---

## Hvad Jarvis kan i fase 1

| Værktøj          | Hvad                                                 |
|------------------|------------------------------------------------------|
| `read_file`      | Læs en tekstfil                                      |
| `write_file`     | Skriv en fil. Overskrivning kræver dit ja            |
| `list_directory` | List en mappe                                        |
| `search_files`   | Søg efter tekst i filer                              |
| `open_path`      | Åbn en fil, eller start et program fra `[programs]`  |

Claude kalder værktøjerne i en løkke og kan altså bruge flere efter
hinanden («find filen med indkøbslisten og læs den op»).

## Sikkerhed

- **Kun tilladte mapper.** Alle stier opløses, før de tjekkes — også `..`,
  genveje og symbolske links — så man ikke kan snyde sig ud af mapperne.
- **Intet overskrives uden dit ja.** Jarvis siger, hvad den vil gøre, og
  venter på, at du holder tasten nede og svarer. Kun et klart «ja» tæller.
  Nej, tavshed i 30 sekunder eller noget uforståeligt betyder nej.
- **Intet slettes eller sendes.** Der findes ingen værktøjer til det i fase 1.
- **Ingen vilkårlige programmer.** Kun dem i `[programs]`. Programfiler
  (`.exe`, `.bat`, `.ps1` osv.) i de tilladte mapper åbnes aldrig.
- **Logbog.** Alt, hvad Jarvis hører, siger og gør, skrives med
  tidsstempel i `logs/jarvis.log`. Indholdet af filer, den skriver, logges
  ikke — kun længden.

## Hukommelse

Samtalen gemmes i `data/jarvis.db` (SQLite). Jarvis husker alt fra i dag,
også efter en genstart. Ved midnat begynder en ny samtale; de gamle ligger
stadig i databasen.

## Bemærkninger

- Hvis Claudes sikkerhedsfilter afviser en harmløs forespørgsel, prøver
  API'et automatisk igen på en anden Claude-model (`fallbacks: "default"`).
- På et dansk tastatur er Ctrl+Alt det samme som AltGr. Ctrl+Alt+J giver
  ikke noget tegn, så den kolliderer ikke med noget.

## Ikke med i fase 1

Vækkeord, Chrome-styring, adgang til LALATOTO's systemer og automatisk
start med Windows. Den sidste er forberedt: `pythonw -m jarvis` kan lægges
i Windows' startmappe, når vi kommer dertil.

## Udvikling

```powershell
pip install -r requirements-dev.txt
python -m pytest
```
