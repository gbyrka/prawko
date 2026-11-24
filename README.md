# Prawko

Nauka działami i próbny egzamin z oficjalnych pytań na prawo jazdy. Strona obsługuje AM, A1, A2, A, B1, B, C1, C, D1, D, T oraz pozwolenie na kierowanie tramwajem. Użytkownik korzysta bez konta, a postęp nauki zapisuje się na jego urządzeniu.

## GitHub Pages

Gotowa strona znajduje się w `docs/`. W ustawieniach repozytorium **Settings → Pages → Build and deployment** wybierz **Deploy from a branch**, gałąź `main` i folder `/docs`. Po zapisaniu ustawień kolejne pushe do `main` publikują stronę automatycznie.

Podgląd lokalny gotowego eksportu:

```sh
python3 -m http.server 8000 --bind 127.0.0.1 --directory docs
```

Strona będzie dostępna pod adresem [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Ręczna aktualizacja katalogu

Do importu potrzebujesz Pythona 3.10+, FFmpeg z libx264, FFprobe i ImageMagick. Pobierz bieżący arkusz, obie paczki multimediów i paczkę tłumaczeń PJM z [publikacji Ministerstwa Infrastruktury](https://www.gov.pl/web/infrastruktura/jak-uzyskac-prawo-jazdy#pytania-egzaminacyjne-na-prawo-jazdy). Umieść je w `sources/` pod nazwami z przykładu albo podaj ich lokalne ścieżki w poleceniu.

```sh
python3 tools/import_catalog.py --pages --version 07.2026 \
  --xlsx sources/katalog.xlsx \
  --media sources/multimedia.zip sources/multimedia2.zip \
  --pjm sources/pjm.zip
```

Import przygotowuje zdjęcia WebP oraz filmy MP4/H.264, sprawdza pulę egzaminacyjną i zapisuje raport w `docs/data/report-*.json`. Raport pokazuje między innymi dodane, usunięte i zmienione pytania. Jeśli pojawią się nowe braki albo rozmiar przekroczy 950 MB, poprzedni eksport pozostaje dostępny. Raport z próby importu znajdziesz w `sources/pages-report.json`. Skrypt korzysta z poprzedniego eksportu i lokalnej pamięci podręcznej w `sources/pages-cache/`, żeby ponownie kodować tylko nowe lub zmienione pliki.

Po sprawdzeniu zmian:

```sh
git add docs
git commit -m "Zaktualizuj katalog pytań"
git push
```

W wydaniu 07.2026 pytania **11150** i **13074** zostały odłożone ze względu na brak plików pod nazwami zapisanymi w arkuszu. Działy nauki można poprawiać w `tools/topic_overrides.json`, używając numerów pytań. Arkusze, źródłowe ZIP-y i cache są lokalne. Do Gita trafia gotowy eksport `docs/`.

Licencja MIT obejmuje kod aplikacji. Materiały egzaminacyjne pochodzą z Ministerstwa Infrastruktury. Zdjęcia i filmy zostały przekodowane na potrzeby strony. [Warunki ponownego wykorzystywania materiałów Ministerstwa Infrastruktury](https://www.gov.pl/web/infrastruktura/ponowne-wykorzystanie-informacji-sektora-publicznego)

## Podgląd deweloperski

Tryb roboczy może pobierać multimedia z Gov.pl podczas korzystania ze strony. Polecenia dla wydania 07.2026:

```sh
mkdir -p sources
curl -fL 'https://www.gov.pl/attachment/a5c6c329-28a5-4274-a1a8-e2813f0a51bd' -o sources/katalog.xlsx

python3 tools/import_catalog.py --version 07.2026 --xlsx sources/katalog.xlsx \
  --remote-media 'https://www.gov.pl/pliki/mi/multimedia_do_pytan.zip' \
                 'https://www.gov.pl/attachment/10d143bf-9e93-4d82-935d-48c89353d3ce' \
  --remote-pjm 'https://www.gov.pl/pliki/mi/pytania_egzaminacyjne_na_prawo_jazdy_tlumaczenia_migowe_12_2025.zip' \
  --activate

python3 tools/serve.py
```

## Testy

```sh
node --test
python3 -m unittest discover -s tests
```
