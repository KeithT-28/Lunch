# Lunch Roulette SG 🍜

A beginner-friendly Streamlit app for finding food near your office in Singapore.

## Features in this first version

- Search by office building, street, MRT station or landmark
- Discover mapped eateries within a selected radius
- Filter by food type and text keywords
- View results on a map
- Save favourites during the current session
- Pick a random lunch option
- Open a place in Google Maps for directions
- Mobile-friendly layout for iPhone and desktop browsers

## Data sources

- **Nominatim / OpenStreetMap**: converts the location you type into coordinates
- **Overpass API / OpenStreetMap**: discovers nearby eateries

Coverage and details depend on community mapping. Ratings, reliable prices, current opening status and queue times are not guaranteed by these sources. The app intentionally does not invent missing details.

Please use public OpenStreetMap services responsibly. Avoid repeatedly running large searches; the app caches search results to reduce requests. For a larger production service, review the data providers' usage policies and consider a hosted/commercial provider.

## Run it on your computer

1. Install Python 3.10 or newer.
2. Download or clone this repository.
3. Open a terminal in the project folder.
4. Install the dependencies:

   ```bash
   pip install -r requirements.txt
   ```

5. Start the app:

   ```bash
   streamlit run app.py
   ```

6. Open the local URL Streamlit prints in your terminal.

## Publish with GitHub + Streamlit Community Cloud

1. Create a GitHub repository called `lunch-roulette-sg`.
2. Upload `app.py`, `requirements.txt`, and `README.md`.
3. Open [Streamlit Community Cloud](https://share.streamlit.io/) and sign in with GitHub.
4. Choose **Create app**, select the repository and branch, and set the main file to `app.py`.
5. Deploy. Open the published URL on your iPhone and optionally add it to your Home Screen through Safari's Share menu.

Hosting plans and provider limits can change; check current terms before relying on it for a long-running app.

## Current limitations / next steps

- Favourites are session-only and do not yet persist across devices.
- No account/login system yet.
- OpenStreetMap may have incomplete food coverage, price ranges, phone numbers or opening hours.
- Walking distance is estimated using straight-line distance; actual walking routes can be longer.
- Opening status and queue estimates are not verified.
- Commercial place APIs can provide different coverage and richer details but may require API keys and billing.

Suggested next version:
1. Persistent favourites and visited history
2. Better cuisine and budget tagging
3. Weekly lunch planner
4. Optional place provider integration for richer ratings/opening hours
