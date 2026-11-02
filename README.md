# Video Codec Scanner

Video Codec Scanner ist ein kostenloses Windows Tool mit deutscher Oberfläche. Es analysiert lokale Videodateien und zeigt technische Daten verständlich und übersichtlich an.

![Version](https://img.shields.io/badge/Version-1.0-19b6b2)
![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078d4)
![Lizenz](https://img.shields.io/badge/Lizenz-GPLv3-blue)

## Funktionen

- Dateien per Auswahl oder Drag and Drop öffnen
- Video und Audiocodecs erkennen
- Bitraten, Auflösung, Bildformat und Framerate anzeigen
- Dauer, Dateigröße und Container auswerten
- Video, Audio und Untertitelspuren auflisten
- Speicherbedarf pro Minute und Bitrate je Megapixel berechnen
- Kompressionsverhältnisse nur bei vorhandener Referenz oder ausdrücklich als Schätzung ausweisen
- PortableApps.com Paket mit eingebettetem `ffprobe`

## Download

Die fertige Windows Version befindet sich unter [Releases](https://github.com/rodneyasl/VideoCodecScanner/releases).

Der PortableApps.com Installer heißt `VideoCodecScannerPortable_1.0_German.paf.exe`. Er enthält alle benötigten Bestandteile und benötigt keine separate Installation von Python oder FFmpeg.

## Verwendung

1. PortableApps.com Installer starten und ein Ziel auswählen.
2. `VideoCodecScannerPortable.exe` öffnen.
3. Eine Videodatei in das Fenster ziehen oder über **Datei wählen** auswählen.
4. **Jetzt scannen** anklicken.

Die Analyse erfolgt vollständig lokal. Videodateien werden nicht hochgeladen.

## Aus dem Quellcode starten

Voraussetzungen:

- Python 3.10 oder neuer
- `ffprobe.exe` oder `MediaInfo.exe` im Programmordner oder im Windows Suchpfad

```powershell
py -3 -m pip install -r requirements.txt
py -3 src\video_codec_scanner.py
```

## Tests

```powershell
py -3 -m unittest -v tests\test_core.py
```

## PortableApps.com Status

Das Paket verwendet das PortableApps.com Format 3.9 und wurde mit dem offiziellen PortableApps.com Installer 3.9.22 erstellt. Die Aufnahme in den offiziellen PortableApps.com Katalog erfordert zusätzlich eine Prüfung und Freigabe durch PortableApps.com.

## Autor

RodneyASL  
[rodneyswelten.de](https://rodneyswelten.de)

## Lizenz

Video Codec Scanner steht unter der GNU General Public License Version 3 oder neuer. Das mit der fertigen Portable Version ausgelieferte FFmpeg beziehungsweise `ffprobe` unterliegt ebenfalls den beigefügten Lizenzhinweisen.
