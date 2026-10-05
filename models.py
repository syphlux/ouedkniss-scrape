"""Infer brand and model from an Ouedkniss listing title.

"Renault Clio 5 2023 Evolution" -> ("Renault", "Clio 5")
"Clio 5 2021 intense"           -> ("Renault", "Clio 5")

Add models to MODELS when you see "Other" or a wrong guess in the dashboard.
Within a brand, longer names are matched first ("Clio 5" before "Clio").
"""
import re
import unicodedata

MODELS = {
    "Renault": ["Clio 5", "Clio 4", "Clio 3", "Clio 2", "Clio Campus", "Clio", "Symbol", "Megane 4", "Megane 3",
                "Megane", "Kangoo", "Captur", "Kadjar", "Koleos", "Arkana", "Austral", "Duster", "Logan",
                "Sandero", "Express", "Taliant", "Fluence", "Scenic", "Trafic", "Master", "Twingo", "Talisman"],
    "Dacia": ["Sandero Stepway", "Sandero", "Logan", "Duster", "Lodgy", "Dokker", "Spring", "Jogger"],
    "Peugeot": ["208", "2008", "301", "308", "3008", "408", "508", "5008", "206", "207", "Partner", "Rifter",
                "Expert", "Boxer", "Bipper", "Landtrek"],
    "Citroen": ["C3 Aircross", "C4 Picasso", "C4 X", "C-Elysee", "C Elysee", "Elysee", "C3", "C4", "C5", "Berlingo",
                "Jumpy", "Jumper", "Nemo", "DS3", "DS4"],
    "Fiat": ["Tipo Sedan", "Tipo", "500X", "500L", "500", "Doblo", "Panda", "Punto", "Fiorino", "Ducato",
             "Scudo", "Qubo", "Egea", "Linea"],
    "Volkswagen": ["Golf 8", "Golf 7", "Golf 6", "Golf", "Polo", "Passat", "Tiguan", "T-Roc", "T-Cross", "Touareg",
                   "Caddy", "Jetta", "Tharu", "Taigo", "Virtus", "Amarok", "Transporter"],
    "Seat": ["Ibiza", "Leon", "Arona", "Ateca", "Tarraco", "Toledo"],
    "Skoda": ["Fabia", "Octavia", "Rapid", "Kamiq", "Karoq", "Kodiaq", "Scala", "Superb"],
    "Toyota": ["Corolla Cross", "Corolla", "Yaris", "Hilux", "Rav4", "RAV 4", "Land Cruiser", "Prado", "C-HR",
               "Fortuner", "Rush", "Hiace"],
    "Hyundai": ["Grand i10", "i10", "i20", "i30", "Accent RB", "Accent", "Elantra", "Creta", "Tucson",
                "Santa Fe", "Kona", "Venue", "Atos", "H1", "H100"],
    "Kia": ["Picanto", "Rio", "Cerato", "Sportage", "Sorento", "Seltos", "Sonet", "Stonic", "KX1", "KX3",
            "Pegas", "K2700", "Carens"],
    "Chery": ["Tiggo 2 Pro", "Tiggo 2", "Tiggo 3", "Tiggo 4 Pro", "Tiggo 4", "Tiggo 7 Pro", "Tiggo 7",
              "Tiggo 8 Pro", "Tiggo 8", "Arrizo 5", "Arrizo", "QQ"],
    "Geely": ["GX3 Pro", "GX3", "Coolray", "Starray", "Emgrand", "Azkarra", "Tugella", "Okavango"],
    "Suzuki": ["Swift", "Celerio", "Alto", "Dzire", "Vitara", "Jimny", "S-Presso", "Baleno", "Ciaz", "Ertiga"],
    "Nissan": ["Micra", "Sunny", "Qashqai", "Juke", "X-Trail", "Navara", "Patrol"],
    "Opel": ["Corsa", "Astra", "Crossland", "Grandland", "Mokka", "Insignia", "Combo"],
    "Ford": ["Fiesta", "Focus", "Ecosport", "Kuga", "Ranger", "Transit", "Puma"],
    "Chevrolet": ["Spark", "Aveo", "Sail", "Cruze", "Optra", "Captiva"],
    "MG": ["MG ZS", "MG5", "MG 5", "ZS", "RX5", "HS", "GT"],
    "Livan": ["X3 Pro", "X3"],
    "Jetta": ["VS5", "VS7", "VA3"],
    "BAIC": ["X35", "X55", "X7", "BJ40"],
    "DFSK": ["Glory", "Seres", "C31", "C35", "C37", "K01"],
    "JAC": ["J7", "JS4", "JS2", "T8", "S3"],
    "Haval": ["Jolion", "H6", "H2"],
    "Great Wall": ["Wingle 7", "Wingle 5", "Wingle", "Poer"],
    "Mitsubishi": ["L200", "Pajero", "Outlander", "ASX", "Attrage", "Space Star"],
    "Mercedes": ["Classe A", "Classe C", "Classe E", "GLA", "GLC", "GLE", "Vito", "Sprinter", "Citan"],
    "BMW": ["Serie 1", "Serie 3", "Serie 5", "X1", "X3", "X5", "X6"],
    "Audi": ["A1", "A3", "A4", "A5", "A6", "Q2", "Q3", "Q5", "Q7"],
    "Mazda": ["Mazda 2", "Mazda 3", "CX-3", "CX-5", "BT-50"],
    "Honda": ["Civic", "Jazz", "City", "CR-V", "HR-V"],
    "Isuzu": ["D-Max", "D Max"],
    "Changan": ["Alsvin", "CS35", "CS55", "CS75"],
}

# Alternate spellings people use for brands.
BRAND_ALIASES = {
    "vw": "Volkswagen", "volkswagen": "Volkswagen", "citroen": "Citroen", "citroën": "Citroen",
    "mercedes-benz": "Mercedes", "mercedes": "Mercedes", "great": "Great Wall", "gwm": "Great Wall",
}


def _norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[\s\-_]+", " ", s).strip()


# (brand, model, normalized regex) sorted so longer model names win.
_PATTERNS = sorted(
    [(b, m, re.compile(r"(?<![a-z0-9])" + re.escape(_norm(m)) + r"(?![a-z0-9])")) for b, ms in MODELS.items() for m in ms],
    key=lambda t: -len(t[1]),
)
_BRANDS = {_norm(b): b for b in MODELS} | BRAND_ALIASES


def infer_brand_model(title):
    t = _norm(title)
    first = t.split(" ")[0] if t else ""
    brand = _BRANDS.get(first)
    if brand is None and t.startswith("great wall"):
        brand = "Great Wall"

    # Prefer a model from the brand named in the title.
    for b, m, rx in _PATTERNS:
        if (brand is None or b == brand) and rx.search(t):
            return b, m

    # Fallback: first word is the brand, up to two words after it (before the year) the model.
    words = title.split()
    year_idx = next((i for i, w in enumerate(words) if re.fullmatch(r"(19|20)\d{2}", w)), len(words))
    if not brand and year_idx >= 2:
        brand = words[0].capitalize()
    guess = " ".join(words[1:year_idx][:2]).strip()
    return brand or "Other", guess or "Other"


if __name__ == "__main__":
    for s in ["Renault Clio 5 2023 Evolution", "Clio 5 2021 intense", "Fiat Tipo Sedan 2023 City Plus",
              "Hyundai Grand I10 2018", "Geely GX3 PRO 2024 Privilège", "Livan X3 Pro 2025 Manuelle",
              "Peugeot 208 2022 Allure", "Achetez Toutes Les Voitures En Panne 2025 Dz"]:
        print(f"{s!r:50} -> {infer_brand_model(s)}")
