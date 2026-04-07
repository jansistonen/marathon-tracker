# Warriors Path Tracker v2

Kevyt Flask-sovellus maratoniseurantaan, nyt valmiina siirtymään Azure App Service + PostgreSQL -malliin.

## Tässä versiossa
- Flask + SQLAlchemy
- paikallisesti SQLite oletuksena
- tuotannossa PostgreSQL `DATABASE_URL`-ympäristömuuttujalla
- osallistujan lisäys
- avatarin valinta emoji-listasta
- duplikaattien esto (`normalized_name`)
- oman profiilin valinta ilman varsinaista kirjautumista (`runner_token`-cookie)
- lenkin lisäys vain omalle profiilille
- viikko- ja kuukausitavoitteet
- streak + viimeisten viikkojen historia
- yhteinen leaderboard-palkki, jonka varrella avatarit näkyvät kokonaiskilometrien mukaan
- arkistointi virheelliselle käyttäjälle
- `/health` health check -reitti

## Mitä tässä ei vielä ole
- oikea kirjautuminen
- CSRF-suojaus
- kuvatiedostojen upload avataria varten
- migraatiot (`Flask-Migrate` tms.)
- admin-roolit

Avatar-kuvien oma upload kannattaa lisätä vasta myöhemmin, koska silloin pitää ratkaista myös tiedostojen tallennus. Azure App Servicen paikallinen tiedostojärjestelmä ei ole hyvä pitkäaikaiseksi käyttäjämedialle; tuotannossa se kannattaa viedä esimerkiksi Blob Storageen. Tästä syystä tässä versiossa avatarit ovat emojit.

## Paikallinen ajo

### 1) Asenna riippuvuudet
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2) Käynnistä sovellus
```bash
python app.py
```

Avaa selaimeen:
```text
http://127.0.0.1:5000
```

### 3) Lisää halutessasi demo-data
```bash
export FLASK_APP=app.py
flask seed-demo
```

Windows PowerShell:
```powershell
$env:FLASK_APP = "app.py"
flask seed-demo
```

## PostgreSQL paikallisesti
Jos haluat kokeilla jo lokaalisti PostgreSQL:llä:

```bash
export DATABASE_URL='postgresql://postgres:postgres@localhost:5432/warriors_path'
python app.py
```

## Azure App Service -deploy
Azure App Service tukee Python-webappeja Linux-ympäristössä, ja Microsoftin Flask + PostgreSQL -tutoriaali käyttää juuri tätä mallia. citeturn616458search0turn616458search6

### Arkkitehtuuri
- **Azure App Service (Linux, Python)** sovellukselle
- **Azure Database for PostgreSQL Flexible Server** tietokannalle
- **GitHub Actions** deployyn

Microsoftin Python-konfigurointiohjeen mukaan Linux App Servicessä voidaan käyttää omaa startup commandia, mikä sopii hyvin Gunicorn-käynnistykseen. citeturn616458search1turn616458search7

### 1) Luo PostgreSQL Flexible Server
Luo Azure-portaalissa **Azure Database for PostgreSQL flexible server**. Microsoftin quickstartin mukaan palvelimelle määritetään palvelinnimi, admin-käyttäjä, salasana ja verkkoasetukset luontivaiheessa. citeturn616458search5

Käytännön vinkki ensimmäiseen versioon:
- valitse **public access** tai ohjattu yhteysvaihtoehto, jotta alkuun pääsee helpommin
- tee oma tietokanta esimerkiksi nimellä `warriorspath`

### 2) Luo App Service
Luo **Web App** näillä asetuksilla:
- Publish: **Code**
- Runtime stack: **Python 3.12**
- Operating System: **Linux**

Azure App Service quickstart kertoo, että Python-appit ajetaan Linux-ympäristössä. citeturn616458search6turn616458search3

### 3) Aseta App Serviceen ympäristömuuttujat
Azure Portal → App Service → **Environment variables** / **Application settings**

Lisää ainakin:
- `SECRET_KEY` = pitkä satunnainen merkkijono
- `DATABASE_URL` = PostgreSQL-yhteysosoite
- `SCM_DO_BUILD_DURING_DEPLOYMENT` = `true`

Esimerkki:
```text
DATABASE_URL=postgresql://dbadmin:YOUR_PASSWORD@your-server.postgres.database.azure.com:5432/warriorspath?sslmode=require
```

Azure PostgreSQL -yhteysohjeissa Python-esimerkit käyttävät tavallista PostgreSQL-yhteyttä, ja Azure Flexible Server tukee Python-kirjastoja kuten psycopg:tä. citeturn616458search2turn616458search13

### 4) Startup command
App Service → **Configuration** → **General settings** → **Startup Command**

Aseta:
```bash
./startup.sh
```

Azure App Service Python -ohjeet tukevat omaa startup commandia Linux-ympäristössä. citeturn616458search1turn616458search7

### 5) GitHub Actions deploy
Tässä projektissa on mukana valmis workflow:
```text
.github/workflows/azure-webapp.yml
```

Lisää GitHub-repon **Secrets and variables → Actions** -kohtaan:
- `AZURE_WEBAPP_NAME`
- `AZURE_WEBAPP_PUBLISH_PROFILE`

Publish Profile haetaan Azure Portalista App Servicen **Get publish profile** -toiminnolla. Azure webapps-deploy -action tukee tätä mallia. citeturn616458search6

### 6) Ensimmäinen deploy
Kun pusket `main`-haaraan, workflow deployaa sovelluksen App Serviceen.

Deployn jälkeen testaa:
- `/health`
- etusivu
- käyttäjän lisäys
- lenkin lisäys

### 7) Yleisimmät ongelmat Azurella
Jos sovellus ei käynnisty:
- tarkista **Log stream**
- varmista startup command
- varmista että `gunicorn` löytyy `requirements.txt`:stä
- varmista että app käynnistyy muodossa `app:app`

Microsoftin App Service -ohjeet korostavat startup commandin ja lokien tarkistusta Python-appien vikatilanteissa. citeturn616458search1turn616458search17

## Ennen oikeaa livekäyttöä
Nämä kannattaa tehdä pian:

1. **CSRF-suojaus** lomakkeille  
2. **Migraatiot** (`Flask-Migrate`)  
3. **Admin-koodi** käyttäjän palautukseen/arkistointiin  
4. **HTTPS only** App Servicessä  
5. **Oikea auth** myöhemmin, jos käyttö kasvaa  
6. **Blob Storage** jos haluat oikeat avatar-kuvat  

## Azure CLI -pikakomennot (valinnainen)
Jos haluat tehdä osan CLI:llä, Microsoftin PostgreSQL- ja App Service -quickstartit tukevat Azure CLI -polkua sekä tietokannan että appin luonnissa. citeturn616458search5turn616458search6turn616458search18
