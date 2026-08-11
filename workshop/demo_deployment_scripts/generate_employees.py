"""Generate the employee master and write it to workshop/data/employees.csv.

Run this occasionally; commit the output. The seed script only loads the CSV, so
the repository is the source of truth and two people seeding from the same commit
get byte-identical data. Everything here is seeded and deterministic - rerunning
without changing the inputs rewrites the same file.

What is deliberate rather than random:

  * Alpine Retail carries the incident. A block of its employees still hold bank
    accounts in the legacy Czech domestic format, because their records were
    migrated in bulk from the previous provider at onboarding and never edited
    since. Those are the rows that reject with VAL-014.
  * A couple of other customers hold a handful of legacy accounts too, so the
    answer to "is this only Alpine?" is interesting rather than trivial.
  * IBANs carry real mod-97 check digits. The file specification says validation
    includes the check digits, so an IBAN that fails its own checksum would be a
    detectable inconsistency in the dataset.

Usage:
    uv run workshop/scripts/generate_employees.py
    uv run workshop/scripts/generate_employees.py --check   # verify, write nothing
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dbx  # noqa: E402

SEED = 20260809

# Czech given names, weighted roughly by how common they actually are.
CZ_MALE = [
    ("Jan", 30), ("Jiří", 28), ("Petr", 26), ("Josef", 22), ("Pavel", 20),
    ("Martin", 19), ("Jaroslav", 17), ("Tomáš", 17), ("Miroslav", 16), ("Zdeněk", 14),
    ("František", 13), ("Václav", 12), ("Michal", 12), ("Milan", 11), ("Lukáš", 11),
    ("David", 10), ("Ladislav", 9), ("Radek", 9), ("Roman", 8), ("Marek", 8),
    ("Vladimír", 8), ("Ondřej", 7), ("Karel", 7), ("Filip", 6), ("Daniel", 6),
    ("Stanislav", 6), ("Antonín", 5), ("Adam", 5), ("Rostislav", 4), ("Vojtěch", 4),
    ("Aleš", 4), ("Libor", 4), ("Dominik", 3), ("Patrik", 3), ("Matěj", 3),
]
CZ_FEMALE = [
    ("Marie", 26), ("Jana", 25), ("Eva", 22), ("Hana", 20), ("Anna", 19),
    ("Lenka", 18), ("Kateřina", 17), ("Věra", 15), ("Lucie", 15), ("Alena", 14),
    ("Petra", 13), ("Jaroslava", 12), ("Veronika", 12), ("Martina", 11), ("Jitka", 11),
    ("Michaela", 10), ("Ludmila", 9), ("Zdeňka", 9), ("Tereza", 9), ("Helena", 8),
    ("Monika", 8), ("Ivana", 8), ("Zuzana", 7), ("Markéta", 7), ("Barbora", 7),
    ("Dagmar", 6), ("Radka", 6), ("Šárka", 5), ("Klára", 5), ("Simona", 4),
    ("Blanka", 4), ("Iveta", 4), ("Renata", 4), ("Miroslava", 4), ("Nikola", 3),
]
CZ_SURNAME = [
    ("Novák", 8), ("Svoboda", 8), ("Novotný", 7), ("Dvořák", 7), ("Černý", 7),
    ("Procházka", 6), ("Kučera", 6), ("Veselý", 6), ("Horák", 6), ("Němec", 5),
    ("Marek", 5), ("Pospíšil", 5), ("Pokorný", 5), ("Hájek", 5), ("Jelínek", 4),
    ("Král", 4), ("Růžička", 4), ("Beneš", 4), ("Fiala", 4), ("Sedláček", 4),
    ("Doležal", 4), ("Zeman", 4), ("Kolář", 4), ("Navrátil", 4), ("Čermák", 3),
    ("Vaněk", 3), ("Urban", 3), ("Blažek", 3), ("Kříž", 3), ("Kovář", 3),
    ("Bartoš", 3), ("Vlček", 3), ("Polák", 3), ("Musil", 3), ("Štěpánek", 3),
    ("Holub", 2), ("Straka", 2), ("Malý", 2), ("Šimek", 2), ("Konečný", 2),
    ("Čech", 2), ("Mareš", 2), ("Soukup", 2), ("Kratochvíl", 2), ("Vávra", 2),
    # Long tail. Without this the common surnames are several times more frequent
    # than they are in reality, and a 2,600-row table reads as a small name pool.
    ("Hruška", 2), ("Dostál", 2), ("Šťastný", 2), ("Kadleček", 2), ("Beránek", 2),
    ("Pekař", 2), ("Sýkora", 2), ("Bláha", 2), ("Barták", 2), ("Vlk", 2),
    ("Matoušek", 2), ("Kopecký", 2), ("Říha", 2), ("Ševčík", 2), ("Zítka", 2),
    ("Kalous", 2), ("Novosad", 2), ("Bezděk", 2), ("Hruban", 2), ("Šindelář", 2),
    ("Doubek", 2), ("Slavík", 2), ("Hlaváček", 2), ("Válek", 2), ("Bureš", 2),
    ("Ryba", 1), ("Kohout", 1), ("Zajíc", 1), ("Liška", 1), ("Ježek", 1),
    ("Sova", 1), ("Špaček", 1), ("Vrána", 1), ("Křeček", 1), ("Motyčka", 1),
    ("Tomek", 1), ("Kvasnička", 1), ("Rypka", 1), ("Šebesta", 1), ("Jandák", 1),
    ("Peterka", 1), ("Loukota", 1), ("Chalupa", 1), ("Zavadil", 1), ("Hrabec", 1),
    ("Fojtík", 1), ("Kavka", 1), ("Bednář", 1), ("Vaníček", 1), ("Přikryl", 1),
    ("Zatloukal", 1), ("Vaculík", 1), ("Hejduk", 1), ("Pešek", 1), ("Kroupa", 1),
    ("Ryšavý", 1), ("Pospíchal", 1), ("Trnka", 1), ("Kubát", 1), ("Rezek", 1),
    ("Foltýn", 1), ("Jirout", 1), ("Kliment", 1), ("Mrázek", 1), ("Šulc", 1),
    ("Havlík", 1), ("Brož", 1), ("Bárta", 1), ("Vondra", 1), ("Duda", 1),
    ("Šmíd", 1), ("Krejčí", 1), ("Tichý", 1), ("Suchý", 1), ("Bílek", 1),
    ("Janda", 1), ("Marek", 1), ("Kraus", 1), ("Skala", 1), ("Havel", 1),
]
SK_MALE = [
    ("Peter", 26), ("Ján", 25), ("Jozef", 22), ("Martin", 18), ("Milan", 16),
    ("Michal", 15), ("Marek", 13), ("Tomáš", 13), ("Miroslav", 12), ("Ľuboš", 9),
    ("Pavol", 12), ("Stanislav", 9), ("Vladimír", 9), ("Róbert", 8), ("Juraj", 8),
    ("Marián", 8), ("Andrej", 6), ("Lukáš", 6), ("Matúš", 5), ("Patrik", 5),
]
SK_FEMALE = [
    ("Mária", 25), ("Anna", 22), ("Zuzana", 18), ("Jana", 17), ("Katarína", 16),
    ("Eva", 15), ("Helena", 12), ("Martina", 11), ("Lucia", 11), ("Monika", 10),
    ("Andrea", 10), ("Veronika", 9), ("Silvia", 8), ("Ivana", 8), ("Michaela", 7),
    ("Gabriela", 6), ("Miriam", 5), ("Simona", 5), ("Adriana", 4), ("Dominika", 4),
]
SK_SURNAME = [
    ("Horváth", 7), ("Kováč", 7), ("Varga", 6), ("Tóth", 6), ("Nagy", 5),
    ("Baláž", 5), ("Szabó", 5), ("Molnár", 4), ("Balog", 4), ("Lukáč", 4),
    ("Gajdoš", 4), ("Král", 4), ("Šimko", 4), ("Hudák", 3), ("Bartoš", 3),
    ("Krajči", 3), ("Ondruš", 3), ("Sedlák", 3), ("Michalík", 3), ("Danko", 3),
    ("Vaník", 2), ("Halaj", 2), ("Bodnár", 2), ("Zelenák", 2), ("Kubík", 2),
    ("Blaho", 2), ("Chovanec", 2), ("Novotný", 2), ("Ivanič", 2), ("Dubovský", 2),
    ("Belan", 2), ("Repka", 2), ("Slávik", 2), ("Ďurica", 2), ("Mihálik", 2),
    ("Benko", 2), ("Petrík", 2), ("Kollár", 2), ("Adamec", 2), ("Fabian", 2),
    ("Hlaváč", 1), ("Uhrík", 1), ("Šuška", 1), ("Rusnák", 1), ("Greguš", 1),
    ("Gubka", 1), ("Matejka", 1), ("Ondrejka", 1), ("Pavlík", 1), ("Sokol", 1),
    ("Cibuľa", 1), ("Struhár", 1), ("Vavro", 1), ("Zeman", 1), ("Bahna", 1),
]

# Bank codes actually in use in each country, so an account looks native.
CZ_BANKS = ["0100", "0300", "0600", "0800", "2010", "2700", "3030", "5500", "6210"]
SK_BANKS = ["0200", "0900", "1100", "3100", "5200", "7500", "8330"]

CONTRACT_TYPES = ["HPP", "HPP part-time", "DPČ", "DPP"]


def weighted(rng: random.Random, pairs: list[tuple[str, int]]) -> str:
    names = [p[0] for p in pairs]
    weights = [p[1] for p in pairs]
    return rng.choices(names, weights=weights, k=1)[0]


def feminine(surname: str) -> str:
    """Czech and Slovak feminine surname forms.

    The fleeting vowel matters: -ek, -ec and -el drop it before the suffix, so
    Jelinek becomes Jelinkova and not Jelinekova. Nemec -> Nemcova is the
    textbook case. Getting this wrong is immediately visible to a Czech reader.
    """
    if surname.endswith("ý"):
        return surname[:-1] + "á"
    if surname.endswith("í"):
        return surname
    if surname.endswith("ek"):
        return surname[:-2] + "ková"
    if surname.endswith("ec"):
        return surname[:-2] + "cová"
    if surname.endswith("el"):
        return surname[:-2] + "lová"
    if surname.endswith("a"):
        return surname[:-1] + "ová"
    return surname + "ová"


def iban_check_digits(country: str, bban: str) -> str:
    """Mod-97-10 check digits per ISO 13616."""
    rearranged = bban + country + "00"
    numeric = "".join(str(ord(ch) - 55) if ch.isalpha() else ch for ch in rearranged)
    return f"{98 - int(numeric) % 97:02d}"


def make_iban(rng: random.Random, country: str) -> tuple[str, str, str, str]:
    """Return (iban, bank_code, prefix, account) for CZ or SK."""
    bank = rng.choice(CZ_BANKS if country == "CZ" else SK_BANKS)
    prefix = f"{rng.randint(0, 999999):06d}" if rng.random() < 0.25 else "000000"
    account = f"{rng.randint(1, 9999999999):010d}"
    bban = f"{bank}{prefix}{account}"
    return f"{country}{iban_check_digits(country, bban)}{bban}", bank, prefix, account


def legacy_format(prefix: str, account: str, bank: str) -> str:
    """The pre-IBAN Czech domestic form: [prefix-]account/bank."""
    acct = account.lstrip("0") or "0"
    pfx = prefix.lstrip("0")
    return f"{pfx}-{acct}/{bank}" if pfx else f"{acct}/{bank}"


def build(cfg: dict, workshop_day: date) -> list[dict]:
    rng = random.Random(SEED)

    clients = {c["client_id"]: c
               for c in json.loads(dbx.data_file(cfg, "clients").read_text(encoding="utf-8"))}
    centres = {c["client_id"]: c["cost_centres"]
               for c in json.loads(dbx.data_file(cfg, "cost_centres").read_text(encoding="utf-8"))}

    # How many employees at each customer still hold a legacy account. Alpine
    # migrated its whole master in bulk at onboarding; the others are stragglers.
    LEGACY = {"CL-001": 47, "CL-005": 3, "CL-011": 1}

    rows: list[dict] = []
    for cid in sorted(clients):
        client = clients[cid]
        if "Payroll" not in client["modules"]:
            continue  # no Payroll module, so no employee master

        country = client["country"]
        male_pool = CZ_MALE if country == "CZ" else SK_MALE
        female_pool = CZ_FEMALE if country == "CZ" else SK_FEMALE
        surname_pool = CZ_SURNAME if country == "CZ" else SK_SURNAME

        ccs = centres[cid]
        headcount = client["employees"]
        # Allocate headcount across cost centres, giving the remainder to the largest.
        alloc = [max(1, round(headcount * cc["headcount_share"])) for cc in ccs]
        drift = headcount - sum(alloc)
        alloc[max(range(len(alloc)), key=lambda i: alloc[i])] += drift

        onboarded = workshop_day - timedelta(days=client["months_as_customer"] * 30)
        legacy_budget = LEGACY.get(cid, 0)
        # Only people already employed when the customer joined Saldo can carry a
        # migrated record, so the legacy accounts are all long-serving staff.
        legacy_candidates: list[int] = []

        seq = 0
        for cc, n in zip(ccs, alloc):
            for _ in range(n):
                seq += 1
                is_female = rng.random() < (0.62 if cc["kind"] in ("store", "clinic", "office") else 0.34)
                first = weighted(rng, female_pool if is_female else male_pool)
                base = weighted(rng, surname_pool)
                last = feminine(base) if is_female else base

                # Hired somewhere in the last 18 years, skewed towards recent.
                years = rng.triangular(0.1, 18.0, 2.5)
                started = workshop_day - timedelta(days=int(years * 365.25))

                if cc["kind"] in ("office", "delivery"):
                    contract = "HPP"
                else:
                    contract = rng.choices(CONTRACT_TYPES, weights=[70, 14, 10, 6], k=1)[0]

                salaried = cc["kind"] in ("office", "delivery") and contract == "HPP"
                if salaried:
                    monthly = rng.randrange(38000, 96000, 500)
                    hourly = None
                else:
                    hourly = rng.randrange(160, 340, 5)
                    monthly = None

                born = rng.randint(1962, 2006)
                pn = f"{born % 100:02d}{rng.randint(1, 12) + (50 if is_female else 0):02d}{rng.randint(1, 28):02d}/{rng.randint(1000, 9999)}"

                iban, bank, prefix, account = make_iban(rng, country)
                rows.append({
                    "employee_id": f"{cid.replace('CL-', 'E')}-{seq:05d}",
                    "client_id": cid,
                    "first_name": first,
                    "last_name": last,
                    "personal_number": pn,
                    "bank_account": iban,
                    "bank_account_format": "IBAN",
                    "cost_centre": cc["code"],
                    "contract_type": contract,
                    "pay_basis": "monthly" if salaried else "hourly",
                    "monthly_salary": monthly,
                    "hourly_rate": hourly,
                    "started_on": started.isoformat(),
                    "ended_on": None,
                    "is_active": True,
                    "record_updated_on": None,   # filled in below
                    "_legacy_parts": (prefix, account, bank),
                    "_started": started,
                })
                if started < onboarded:
                    legacy_candidates.append(len(rows) - 1)

        # Turn a deliberate subset of long-serving records back into legacy accounts,
        # spread across cost centres rather than clustered in one place.
        if legacy_budget:
            rng.shuffle(legacy_candidates)
            chosen = sorted(legacy_candidates[:legacy_budget])
            for idx in chosen:
                r = rows[idx]
                prefix, account, bank = r["_legacy_parts"]
                r["bank_account"] = legacy_format(prefix, account, bank)
                r["bank_account_format"] = "legacy_domestic"

        # record_updated_on: legacy rows were last touched at migration and never
        # since, which is exactly what makes them the ones that fail.
        for r in rows:
            if r["client_id"] != cid:
                continue
            if r["bank_account_format"] == "legacy_domestic":
                r["record_updated_on"] = onboarded.isoformat()
            else:
                latest = max(r["_started"], onboarded)
                span = max((workshop_day - latest).days, 1)
                r["record_updated_on"] = (latest + timedelta(days=rng.randint(0, span))).isoformat()

    for r in rows:
        del r["_legacy_parts"]
        del r["_started"]
    return rows


COLUMNS = ["employee_id","client_id","first_name","last_name","personal_number","bank_account",
           "bank_account_format","cost_centre","contract_type","pay_basis","monthly_salary",
           "hourly_rate","started_on","ended_on","is_active","record_updated_on"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", help="workshop date as YYYY-MM-DD (overrides the config)")
    ap.add_argument("--check", action="store_true", help="build and validate, write nothing")
    args = ap.parse_args()

    cfg = dbx.load_config()
    pinned = args.date or cfg.get("workshop", {}).get("date")
    workshop_day = date.fromisoformat(str(pinned)) if pinned else date.today()

    rows = build(cfg, workshop_day)

    # Every IBAN must pass its own checksum.
    bad = []
    for r in rows:
        if r["bank_account_format"] != "IBAN":
            continue
        acct = r["bank_account"]
        if iban_check_digits(acct[:2], acct[4:]) != acct[2:4]:
            bad.append(r["employee_id"])
    if bad:
        raise SystemExit(f"{len(bad)} IBANs fail their own checksum, first: {bad[:3]}")

    legacy = [r for r in rows if r["bank_account_format"] == "legacy_domestic"]
    print(f"employees              {len(rows)}")
    print(f"legacy bank accounts   {len(legacy)}")
    for cid in sorted({r['client_id'] for r in legacy}):
        n = sum(1 for r in legacy if r["client_id"] == cid)
        centres = len({r["cost_centre"] for r in legacy if r["client_id"] == cid})
        print(f"   {cid}  {n:>3}  across {centres} cost centres")
    print("all IBAN checksums     valid")

    if args.check:
        print("\nnothing written (--check)")
        return 0

    out = dbx.data_file(cfg, "employees")
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nwrote {out.relative_to(dbx.REPO_ROOT)}  ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
