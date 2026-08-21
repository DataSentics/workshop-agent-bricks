# Databricks notebook source
# MAGIC %md
# MAGIC # 🧭 Hands-on: Incident Alpine Retail
# MAGIC
# MAGIC Vítejte v praktické části workshopu **Agent Bricks**.
# MAGIC
# MAGIC V následujících krocích se vžijete do role člena **support týmu společnosti Saldo** a budete řešit skutečně vypadající zákaznický incident.
# MAGIC
# MAGIC Nejdříve si problém vyšetříme s pomocí několika **specializovaných agentů a datových zdrojů**. Postupně uvidíme, že každý z nich zná pouze část celého příběhu.
# MAGIC
# MAGIC Nakonec si ukážeme, jak jejich schopnosti spojit pomocí **Supervisor Agenta**, aby support specialista nemusel jednotlivé systémy a agenty obsluhovat ručně.
# MAGIC
# MAGIC > 🎯 **Cílem** je pochopit, jak lze pomocí specializovaných agentů a nástrojů zjednodušit vyšetřování komplexního zákaznického incidentu.
# MAGIC

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🏢 Kdo jsme?
# MAGIC
# MAGIC V tomto scénáři pracujeme pro společnost **Saldo**.
# MAGIC
# MAGIC **Saldo provozuje cloudovou platformu, kterou jiné firmy používají ke zpracování mezd svých zaměstnanců.**
# MAGIC
# MAGIC Jedním z našich zákazníků je **Alpine Retail** — maloobchodní společnost působící v Česku a na Slovensku.
# MAGIC
# MAGIC Zjednodušeně:
# MAGIC
# MAGIC ```text
# MAGIC Alpine Retail
# MAGIC (zaměstnavatel)
# MAGIC       │
# MAGIC       │ používá
# MAGIC       ▼
# MAGIC     SALDO
# MAGIC (cloudová payroll platforma)
# MAGIC       │
# MAGIC       │ zpracovává
# MAGIC       ▼
# MAGIC mzdy zaměstnanců Alpine Retail

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🚨 Máme problém
# MAGIC
# MAGIC Alpine Retail právě dokončil pravidelné zpracování mezd.
# MAGIC
# MAGIC Výsledek ale není v pořádku:
# MAGIC
# MAGIC ### **47 zaměstnanců Alpine Retail nedostalo výplatu.**
# MAGIC
# MAGIC Zákazník se obrací na support společnosti Saldo a očekává vysvětlení a řešení.
# MAGIC
# MAGIC Představte si, že jste support specialista, který tento incident právě dostal na starost.
# MAGIC
# MAGIC Potřebujete zjistit:
# MAGIC
# MAGIC 1. 🔎 **Co se při zpracování mezd přesně stalo?**
# MAGIC 2. ❓ **Proč bylo právě 47 zaměstnanců zamítnuto?**
# MAGIC 3. 🌍 **Je problém pouze u Alpine Retail, nebo se týká více zákazníků?**
# MAGIC 4. 🛠️ **Změnilo se na platformě Saldo něco, co mohlo problém způsobit?**
# MAGIC 5. ⚖️ **Je příčina na straně zákazníka, nebo na straně Salda?**
# MAGIC 6. 📄 **Co o podobné situaci říká dokumentace a smlouva se zákazníkem?**
# MAGIC 7. 💰 **Má zákazník nárok na kompenzaci / SLA credit?**
# MAGIC 8. ✉️ **Co zákazníkovi odpovíme a jak aktualizujeme jeho support case?**
# MAGIC
# MAGIC > Automatizujeme a zjednodušujeme **práci support specialisty při vyšetřování komplexního incidentu**.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🧑‍💻 Jak by incident vyšetřoval support specialista?
# MAGIC
# MAGIC Aby support specialista zjistil skutečnou příčinu, musí typicky pracovat s několika různými zdroji:
# MAGIC
# MAGIC ```text
# MAGIC                        SUPPORT SPECIALISTA
# MAGIC                               │
# MAGIC          ┌────────────────────┼─────────────────────┐
# MAGIC          │                    │                     │
# MAGIC          ▼                    ▼                     ▼
# MAGIC    Payroll data           Platform data        Dokumentace
# MAGIC          │                    │                     │
# MAGIC          ▼                    ▼                     ▼
# MAGIC   Support cases          Změny / releasy          Smlouvy
# MAGIC          │
# MAGIC          ▼
# MAGIC   Komunikace se zákazníkem

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🗂️ Jaká data má Saldo k dispozici?
# MAGIC
# MAGIC Pro vyšetření incidentu máme k dispozici dvě hlavní datové domény:
# MAGIC
# MAGIC ### 1️⃣ Payroll Operations
# MAGIC
# MAGIC Obsahuje data o zákaznících, zaměstnancích a zpracování mezd.
# MAGIC
# MAGIC Patří sem například:
# MAGIC
# MAGIC - zákazníci Salda,
# MAGIC - kontaktní osoby,
# MAGIC - zaměstnanci,
# MAGIC - payroll runs,
# MAGIC - výsledky payrollu pro jednotlivé zaměstnance,
# MAGIC - validační chyby a jejich význam.
# MAGIC
# MAGIC ### 2️⃣ Platform Health
# MAGIC
# MAGIC Obsahuje data o samotném provozu platformy Saldo.
# MAGIC
# MAGIC Patří sem například:
# MAGIC
# MAGIC - dostupnost služeb,
# MAGIC - provozní incidenty,
# MAGIC - změny a releasy,
# MAGIC - support cases.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 💰 Payroll Operations
# MAGIC
# MAGIC Začneme daty, která popisují **zákazníky Salda a zpracování jejich mezd**.
# MAGIC
# MAGIC Datová doména **Payroll Operations** obsahuje například informace o:
# MAGIC
# MAGIC - zákaznících Salda,
# MAGIC - jejich zaměstnancích,
# MAGIC - pobočkách a nákladových střediscích,
# MAGIC - jednotlivých mzdových bězích,
# MAGIC - výsledku zpracování každého zaměstnance,
# MAGIC - důvodech případného zamítnutí.
# MAGIC
# MAGIC Pro náš incident jsou to data, která nám mohou pomoci odpovědět například na otázku:
# MAGIC
# MAGIC > **Co se při posledním payrollu Alpine Retail skutečně stalo?**
# MAGIC
# MAGIC Nejdřív se jen zorientujeme v tom, **jaké tabulky máme k dispozici a co přibližně obsahují**.

# COMMAND ----------

CATALOG = "sbox_aut_eg00_catalog"
OPS_SCHEMA = "agent_bricks_ws_saldo_ops"

payroll_tables = [
    "clients",
    "contacts",
    "client_modules",
    "cost_centres",
    "reason_codes",
    "employees",
    "payroll_runs",
    "payroll_run_items",
]

for table in payroll_tables:
    print(f"\n📋 {table}")
    display(
        spark.table(f"{CATALOG}.{OPS_SCHEMA}.{table}")
             .limit(5)
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ### 🏥 Platform Health
# MAGIC
# MAGIC Payroll Operations nám ukazuje, **co se děje u zákazníků a jejich mezd**.
# MAGIC
# MAGIC Pro vyšetření incidentu ale potřebujeme znát také druhou stranu příběhu:
# MAGIC
# MAGIC > **Co se v té době dělo na samotné platformě Saldo?**
# MAGIC
# MAGIC Proto máme samostatnou datovou doménu **Platform Health**.
# MAGIC
# MAGIC Ta obsahuje například informace o:
# MAGIC
# MAGIC - dostupnosti služeb,
# MAGIC - provozních incidentech,
# MAGIC - změnách a releasech,
# MAGIC - support cases,
# MAGIC - interních poznámkách k případům.
# MAGIC
# MAGIC Stejně jako předtím se teď jen zorientujeme v tom, **jaké tabulky máme k dispozici a co přibližně obsahují**.

# COMMAND ----------

PLATFORM_SCHEMA = "agent_bricks_ws_saldo_platform"

platform_tables = [
    "service_availability_daily",
    "support_cases",
    "case_notes",
    "incidents",
    "changes",
]

for table in platform_tables:
    print(f"\n📋 {table}")
    display(
        spark.table(f"{CATALOG}.{PLATFORM_SCHEMA}.{table}")
             .limit(5)
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🤖 Od dat ke specializovaným Genie Agents
# MAGIC
# MAGIC Teď už jsme viděli, jaká strukturovaná data má Saldo k dispozici.
# MAGIC
# MAGIC Máme například:
# MAGIC
# MAGIC - informace o zákaznících a zaměstnancích,
# MAGIC - historii mzdových běhů,
# MAGIC - výsledky validací,
# MAGIC - support cases,
# MAGIC - incidenty,
# MAGIC - změny nasazené na platformě.
# MAGIC
# MAGIC To je skvělý základ pro vyšetřování incidentu.
# MAGIC
# MAGIC Otázky support specialisty ale nevycházejí z názvů tabulek a sloupců. Vypadají spíš takto:
# MAGIC
# MAGIC > **„Co se stalo při posledním payrollu Alpine Retail?“**
# MAGIC
# MAGIC nebo:
# MAGIC
# MAGIC > **„Nestala se před tímto problémem nějaká změna na platformě?“**
# MAGIC
# MAGIC A právě tady využijeme **Genie Agents**.
# MAGIC
# MAGIC ### 🧠 Specialista nad konkrétní datovou doménou
# MAGIC
# MAGIC V našem řešení máme dva:
# MAGIC
# MAGIC **💰 Saldo payroll operations**  
# MAGIC Specialista nad daty o zákaznících, zaměstnancích a zpracování mezd.
# MAGIC
# MAGIC **🏥 Saldo platform health**  
# MAGIC Specialista nad daty o provozu platformy, incidentech, změnách a support cases.
# MAGIC
# MAGIC Každý pracuje nad **jiným kontextem a jinými daty**.
# MAGIC
# MAGIC V následujícím kroku se podíváme, jak jsou tito agenti nakonfigurováni — a potom si jejich specializaci vyzkoušíme v praxi.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🧪 Podívejme se na Genie Agents zblízka
# MAGIC
# MAGIC Než začneme incident vyšetřovat, podíváme se, **jak jsou naši dva Genie Agents nakonfigurováni**.
# MAGIC
# MAGIC ### 👉 Otevřete Genie Agents
# MAGIC
# MAGIC V levém menu Databricks otevřete **Genie Agents** a najděte:
# MAGIC
# MAGIC - 💰 **Saldo payroll operations**
# MAGIC - 🏥 **Saldo platform health**
# MAGIC
# MAGIC Začněte agentem **Saldo payroll operations**.
# MAGIC
# MAGIC Při prohlídce jeho konfigurace si všimněte především:
# MAGIC
# MAGIC 1. 📊 **Data** – ke kterým tabulkám má agent přístup?
# MAGIC 2. 📝 **Instructions** – jaké instrukce jsme agentovi dali?
# MAGIC 3. 💬 **Example questions** – jaké příklady otázek jsme mu poskytli?
# MAGIC
# MAGIC Potom stejným způsobem otevřete **Saldo platform health**.
# MAGIC
# MAGIC ### 💡 Čeho si všimnout?
# MAGIC
# MAGIC Oba jsou Genie Agents, ale nejsou nakonfigurováni stejně.
# MAGIC
# MAGIC Každý dostal:
# MAGIC
# MAGIC - jinou množinu dat,
# MAGIC - jinou oblast odpovědnosti,
# MAGIC - jiné instrukce,
# MAGIC - jiné příklady otázek.
# MAGIC
# MAGIC Právě tím z obecné technologie vytváříme **specializovaného agenta pro konkrétní business doménu**.
# MAGIC
# MAGIC
# MAGIC ## 🔬 Experiment: kde končí kompetence agenta?
# MAGIC
# MAGIC Teď vyzkoušíme oba agenty na stejných otázkách.
# MAGIC
# MAGIC ### Otázka 1 – payroll
# MAGIC
# MAGIC Položte **oběma** agentům stejnou otázku:
# MAGIC
# MAGIC > **Kolik zaměstnanců Alpine Retail bylo při posledním mzdovém běhu zamítnuto a z jakého důvodu?**
# MAGIC
# MAGIC 💰 **Saldo payroll operations** by měl dokázat najít konkrétní odpověď v payrollových datech.
# MAGIC
# MAGIC 🏥 **Saldo platform health** detailní výsledky payrollu k dispozici nemá.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Otázka 2 – změny platformy
# MAGIC
# MAGIC Nyní opět položte **oběma** agentům:
# MAGIC
# MAGIC > **Jaké změny byly nasazeny na platformě Saldo těsně před problémem Alpine Retail a mohla některá z nich s problémem souviset?**
# MAGIC
# MAGIC Tentokrát očekáváme opačnou situaci.
# MAGIC
# MAGIC 🏥 **Saldo platform health** má k dispozici historii změn platformy.
# MAGIC
# MAGIC 💰 **Saldo payroll operations** tuto datovou doménu nemá.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🧠 Co jsme experimentem ukázali?
# MAGIC
# MAGIC Každý z nich je **specialista na jinou část problému**.
# MAGIC
# MAGIC ```text
# MAGIC 💰 Payroll Operations             🏥 Platform Health
# MAGIC         │                                │
# MAGIC         │                                │
# MAGIC         ▼                                ▼
# MAGIC  Co se stalo při payrollu?       Co se dělo na platformě?
# MAGIC  Proč byly záznamy odmítnuty?    Co jsme nasadili?
# MAGIC  Kterých zaměstnanců se to týká? Byl incident nebo výpadek?

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🕵️ Proč problém vznikl právě teď?
# MAGIC
# MAGIC První část vyšetřování máme za sebou.
# MAGIC
# MAGIC 💰 **Saldo payroll operations** nám ukázal:
# MAGIC
# MAGIC - 47 zaměstnanců bylo zamítnuto,
# MAGIC - všichni skončili s chybou `VAL-014`,
# MAGIC - problém souvisí s bankovními účty, které nejsou ve formátu IBAN.
# MAGIC
# MAGIC Tím jsme ale ještě nevysvětlili jednu důležitou věc:
# MAGIC
# MAGIC > 🤔 **Proč stejné bankovní účty fungovaly dříve a problém se objevil až teď?**
# MAGIC
# MAGIC To už není otázka na payrollová data.
# MAGIC
# MAGIC Potřebujeme zjistit, **co se změnilo na samotné platformě Saldo**.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🏥 Přecházíme na Saldo platform health
# MAGIC
# MAGIC Otevřete Genie Agenta **Saldo platform health** a položte mu:
# MAGIC
# MAGIC > 💬 **Jaké změny byly nasazeny na platformě Saldo těsně před problémem Alpine Retail a mohla některá z nich s problémem souviset?**
# MAGIC
# MAGIC
# MAGIC ### 🎯 Co jsme zjistili?
# MAGIC
# MAGIC Oba Genie Agents nám dali jinou část odpovědi.
# MAGIC
# MAGIC | 💰 Payroll Operations | 🏥 Platform Health |
# MAGIC |---|---|
# MAGIC | **47 zaměstnanců zamítnuto** | **Release 2026.8** |
# MAGIC | chyba `VAL-014` | změna `CHG-0488` |
# MAGIC | neplatný formát IBAN | odstranění automatické konverze CZ účtů na IBAN |
# MAGIC
# MAGIC ### 🔗 Když obě zjištění spojíme...
# MAGIC
# MAGIC **47 zaměstnanců Alpine Retail mělo bankovní účet ve starém českém formátu.**
# MAGIC
# MAGIC ⬇️
# MAGIC
# MAGIC **Release 2026.8 odstranil automatickou konverzi těchto účtů na IBAN.**
# MAGIC
# MAGIC ⬇️
# MAGIC
# MAGIC **Payroll je proto odmítl s chybou `VAL-014`.**
# MAGIC
# MAGIC > 💡 **Máme velmi pravděpodobnou příčinu incidentu.**

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🧩 Máme incident vyřešený?
# MAGIC
# MAGIC Udělali jsme velký krok dopředu.
# MAGIC
# MAGIC Pomocí dvou specializovaných Genie Agents jsme zjistili:
# MAGIC
# MAGIC ### 💰 Payroll Operations
# MAGIC **Co se stalo?**
# MAGIC
# MAGIC 47 zaměstnanců Alpine Retail bylo při posledním payrollu zamítnuto s chybou `VAL-014`, která souvisí s neplatným formátem bankovního účtu.
# MAGIC
# MAGIC ### 🏥 Platform Health
# MAGIC **Proč se problém objevil právě teď?**
# MAGIC
# MAGIC Krátce před problémem byl nasazen release `2026.8`, který odstranil automatickou konverzi starých českých bankovních účtů na IBAN.
# MAGIC
# MAGIC Máme tedy velmi pravděpodobnou souvislost:
# MAGIC
# MAGIC ```text
# MAGIC 47 zaměstnanců má starý formát účtu
# MAGIC                 │
# MAGIC                 ▼
# MAGIC         dříve fungovala
# MAGIC      automatická konverze
# MAGIC                 │
# MAGIC                 ▼
# MAGIC        release 2026.8
# MAGIC                 │
# MAGIC                 ▼
# MAGIC     automatická konverze
# MAGIC           odstraněna
# MAGIC                 │
# MAGIC                 ▼
# MAGIC           VAL-014
# MAGIC                 │
# MAGIC                 ▼
# MAGIC      47 zaměstnanců
# MAGIC          REJECTED

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🤔 Co ještě support potřebuje zjistit?
# MAGIC
# MAGIC Vraťme se k původnímu úkolu.
# MAGIC
# MAGIC Alpine Retail nechce slyšet pouze:
# MAGIC
# MAGIC > *„Našli jsme `VAL-014`.“*
# MAGIC
# MAGIC Zákazník potřebuje vědět **co se stalo, proč se to stalo a co bude následovat**.
# MAGIC
# MAGIC Než může support případ uzavřít, zbývá několik důležitých otázek:
# MAGIC
# MAGIC ### 📚 Co říká dokumentace?
# MAGIC
# MAGIC Byla změna formátu bankovních účtů někde popsána?
# MAGIC
# MAGIC Jak má zákazník správně opravit svá data?
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 📄 Co říká smlouva?
# MAGIC
# MAGIC Jaké podmínky má Alpine Retail sjednané?
# MAGIC
# MAGIC Má v podobné situaci nárok na kompenzaci?
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🔎 Řešili jsme něco podobného dříve?
# MAGIC
# MAGIC Existují historické support cases se stejným nebo podobným problémem?
# MAGIC
# MAGIC Jak byly vyřešeny?
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 📧 Co jsme zákazníkovi komunikovali?
# MAGIC
# MAGIC Byl Alpine Retail o změně předem informován?
# MAGIC
# MAGIC Existuje relevantní e-mailová komunikace?
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 💰 Má zákazník nárok na SLA credit?
# MAGIC
# MAGIC Pokud ano, jaká je jeho přesná výše?
# MAGIC
# MAGIC Takové rozhodnutí nechceme nechat na odhadu jazykového modelu — potřebujeme spolehlivý a auditovatelný výpočet.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🎫 A co samotný support case?
# MAGIC
# MAGIC Nakonec potřebujeme výsledky vyšetřování zaznamenat a případ posunout dál.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC > 💡 **Technickou příčinu už známe. Teď potřebujeme propojit technické vyšetřování s dokumentací, historií, komunikací a business pravidly.**

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🧩 Jeden incident, více specialistů
# MAGIC
# MAGIC U našeho incidentu jsme zatím potřebovali dva specializované Genie Agents:
# MAGIC
# MAGIC - 💰 **Payroll Genie** → co se stalo při zpracování mezd?
# MAGIC - 🏥 **Platform Health Genie** → co se v té době změnilo na platformě?
# MAGIC
# MAGIC U reálného incidentu ale může být potřeba mnohem víc.
# MAGIC
# MAGIC Můžeme potřebovat:
# MAGIC
# MAGIC - 📚 dohledat informace v dokumentaci a smlouvách,
# MAGIC - 🔎 najít podobné historické support cases,
# MAGIC - 📧 zkontrolovat komunikaci se zákazníkem,
# MAGIC - 🧮 vypočítat případný SLA credit,
# MAGIC - 🎫 přečíst nebo aktualizovat support case.
# MAGIC
# MAGIC Každý z těchto kroků může využívat **jiného specializovaného agenta nebo nástroj**.
# MAGIC
# MAGIC A tady vzniká nový problém:
# MAGIC
# MAGIC > **Kdo rozhodne, kterého specialistu použít, v jakém pořadí a jak jejich výsledky spojit dohromady?**

# COMMAND ----------

# MAGIC %md
# MAGIC # 🧠 Od specialistů k orchestraci
# MAGIC
# MAGIC V první části jsme incident Alpine Retail vyšetřovali pomocí dvou specializovaných Genie Agents:
# MAGIC
# MAGIC - 💰 **Saldo Payroll Operations** — zná zákazníky, zaměstnance a mzdové běhy
# MAGIC - 🏥 **Saldo Platform Health** — zná incidenty, změny a provoz platformy
# MAGIC
# MAGIC Každý z nich je dobrý ve své vlastní oblasti.
# MAGIC
# MAGIC U reálného support incidentu ale často potřebujeme mnohem víc než dvě datové domény.
# MAGIC
# MAGIC Můžeme potřebovat:
# MAGIC
# MAGIC - 📚 najít informace v dokumentaci nebo smlouvách,
# MAGIC - 🔎 dohledat podobné historické případy,
# MAGIC - 🧮 provést přesný business výpočet,
# MAGIC - 📧 pracovat s komunikací se zákazníkem,
# MAGIC - 🎫 přečíst nebo aktualizovat support case.
# MAGIC
# MAGIC A právě tady vzniká nový problém:
# MAGIC
# MAGIC > **Kdo rozhodne, kterého specialistu nebo nástroj použít, co mu zadat a jak výsledky jednotlivých kroků spojit?**
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## 🎯 Supervisor Agent
# MAGIC
# MAGIC K tomu použijeme **Supervisor Agenta**.
# MAGIC
# MAGIC Supervisor nemusí sám znát odpověď na každou otázku.
# MAGIC
# MAGIC Jeho úkolem je **orchestrace**:
# MAGIC
# MAGIC **pochopit úkol → vybrat vhodné specialisty a nástroje → zadat jim dílčí úkoly → vyhodnotit výsledky → rozhodnout o dalším kroku → sestavit výslednou odpověď**
# MAGIC
# MAGIC Postupně mu proto zpřístupníme několik různých specializovaných komponent:
# MAGIC
# MAGIC | Komponenta | K čemu ji použijeme |
# MAGIC |---|---|
# MAGIC | 💰 Payroll Genie | data o payrollu a zaměstnancích |
# MAGIC | 🏥 Platform Health Genie | incidenty, releasy a změny platformy |
# MAGIC | 📚 Knowledge Assistant | dokumentace, návody a smlouvy |
# MAGIC | 🔎 AI Search | podobné historické support případy |
# MAGIC | 🧮 UC Function | přesný výpočet SLA kreditu |
# MAGIC | 📧 Outlook | komunikace se zákazníkem |
# MAGIC | 🎫 CaseHub | práce se support casem |
# MAGIC
# MAGIC > 💡 **Důležitá myšlenka**
# MAGIC >
# MAGIC > Nesnažíme se vytvořit jednoho obřího agenta, který umí všechno.
# MAGIC >
# MAGIC > Jednotlivé komponenty mají **jasně vymezenou odpovědnost** a Supervisor rozhoduje, kdy kterou z nich použít.
# MAGIC >
# MAGIC > Díky tomu lze jednotlivé části samostatně konfigurovat, testovat, zabezpečit a znovu používat.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🛠️ Jdeme stavět
# MAGIC
# MAGIC V následujících krocích budeme pracovat především v **Agent Bricks UI**.
# MAGIC
# MAGIC Tento notebook si nechte otevřený — bude sloužit jako **průvodce jednotlivými kroky** a zároveň vysvětlí, proč jednotlivé komponenty do řešení přidáváme.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🛠️ Krok 1 — Vytvoříme Supervisor Agenta
# MAGIC
# MAGIC Začneme vytvořením prázdného **Supervisor Agenta**.
# MAGIC
# MAGIC Supervisor zatím nebude mít žádné specialisty ani znalosti. Ty mu budeme přidávat postupně.
# MAGIC
# MAGIC ### 👣 Postup
# MAGIC
# MAGIC 1. Otevřete **Agent Bricks**
# MAGIC 2. Klikněte na **Create Agent**
# MAGIC 3. Vyberte **Supervisor Agent**
# MAGIC 4. Zvolte název svého Supervisora
# MAGIC 5. Otevřete jeho záložku **Build**
# MAGIC
# MAGIC Měli byste se dostat na obrazovku podobnou této:
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🧠 Z čeho se Supervisor skládá?
# MAGIC
# MAGIC Na obrazovce **Build** nás budou zajímat především dvě části:
# MAGIC
# MAGIC #### 🧰 Tools and sub-agents
# MAGIC
# MAGIC Sem budeme přidávat všechny specialisty a nástroje, které může Supervisor při řešení úkolu použít.
# MAGIC
# MAGIC Mohou to být například:
# MAGIC
# MAGIC - Genie Spaces
# MAGIC - Knowledge Assistants
# MAGIC - AI Search indexes
# MAGIC - UC Functions
# MAGIC - externí aplikace a služby
# MAGIC
# MAGIC Supervisor potom sám rozhoduje, **který z dostupných nástrojů je pro konkrétní krok vhodný**.
# MAGIC
# MAGIC #### 📝 Instructions
# MAGIC
# MAGIC Instructions určují **jak má Supervisor přemýšlet a pracovat**.
# MAGIC
# MAGIC Budeme zde definovat například:
# MAGIC
# MAGIC - jakou roli Supervisor zastává,
# MAGIC - k čemu má jednotlivé specialisty používat,
# MAGIC - jak má postupovat při vyšetřování incidentu,
# MAGIC - kdy má pokračovat v hledání a kdy už má dostatek informací,
# MAGIC - jak má pracovat s akcemi vyžadujícími schválení.
# MAGIC
# MAGIC > 💡 **Tools říkají Supervisorovi, co má k dispozici.  
# MAGIC > Instructions mu říkají, jak to má používat.**
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🚧 Zatím nic složitého
# MAGIC
# MAGIC Supervisor je v tuto chvíli pouze prázdný orchestrátor.
# MAGIC
# MAGIC V dalších krocích mu postupně přidáme jednotlivé specialisty a u každého si vysvětlíme:
# MAGIC
# MAGIC **co umí → nad jakými daty pracuje → proč ho potřebujeme → jak ho připojit**

# COMMAND ----------

# MAGIC %md
# MAGIC ## 💰🏥 Krok 2 — Připojíme první specialisty
# MAGIC
# MAGIC Začneme dvěma Genie Agents, které už známe z první části workshopu:
# MAGIC
# MAGIC - 💰 **Saldo payroll operations**
# MAGIC - 🏥 **Saldo platform health**
# MAGIC
# MAGIC Doteď jsme se každého z nich ptali samostatně.
# MAGIC
# MAGIC Teď je připojíme k Supervisorovi jako **sub-agenty**.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 👣 Přidáme Payroll Operations
# MAGIC
# MAGIC V části **Tools and sub-agents**:
# MAGIC
# MAGIC 1. Klikněte na **Add a Genie Space**
# MAGIC 2. Vyhledejte `Saldo payroll operations`
# MAGIC 3. Vyberte jej a přidejte k Supervisorovi
# MAGIC
# MAGIC ### 👣 Přidáme Platform Health
# MAGIC
# MAGIC Stejným způsobem:
# MAGIC
# MAGIC 1. Klikněte znovu na **Add a Genie Space**
# MAGIC 2. Vyhledejte `Saldo platform health`
# MAGIC 3. Přidejte jej k Supervisorovi
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC Náš Supervisor má nyní dva specialisty:
# MAGIC
# MAGIC | Specialista | Co zná |
# MAGIC |---|---|
# MAGIC | 💰 **Payroll Operations** | zákazníky, zaměstnance, payroll runs, výsledky zpracování a důvody zamítnutí |
# MAGIC | 🏥 **Platform Health** | support cases, incidenty, změny, releasy a provoz platformy |
# MAGIC
# MAGIC ```text
# MAGIC                     🧠 Supervisor
# MAGIC                     /            \
# MAGIC                    /              \
# MAGIC         💰 Payroll Genie      🏥 Platform Genie

# COMMAND ----------

# MAGIC %md
# MAGIC ## 📚 Krok 3 — Přidáme znalosti z dokumentů
# MAGIC
# MAGIC Doteď jsme pracovali se **strukturovanými daty v tabulkách**.
# MAGIC
# MAGIC Na ně se skvěle hodí Genie:
# MAGIC
# MAGIC 📊 **Tabulky** → 🧞 **Genie Agent** → odpovědi nad strukturovanými daty
# MAGIC
# MAGIC V reálné firmě ale velká část znalostí není v tabulkách.
# MAGIC
# MAGIC Může být například v:
# MAGIC
# MAGIC - 📄 produktové dokumentaci,
# MAGIC - 📄 návodech a provozních postupech,
# MAGIC - 📄 smlouvách,
# MAGIC - 📄 PDF dokumentech,
# MAGIC - 📄 Markdown (`.md`) souborech.
# MAGIC
# MAGIC Pro práci s takovým obsahem použijeme **Knowledge Assistant**.
# MAGIC
# MAGIC 📄 **Dokumenty** → 📁 **Volume** → 📚 **Knowledge Assistant** → 🧠 **Supervisor**
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🧠 Genie vs. Knowledge Assistant
# MAGIC
# MAGIC Je dobré tyto dva specialisty rozlišovat:
# MAGIC
# MAGIC | | 🧞 Genie Agent | 📚 Knowledge Assistant |
# MAGIC |---|---|---|
# MAGIC | **Typický zdroj** | tabulky | dokumenty |
# MAGIC | **Typ informací** | strukturovaná data | textové znalosti |
# MAGIC | **Příklad otázky** | Kolik zaměstnanců bylo zamítnuto? | Co říká dokumentace k chybě VAL-014? |
# MAGIC | **Další příklad** | Který payroll run selhal? | Jak má zákazník chybu napravit? |
# MAGIC
# MAGIC Jednoduchá pomůcka:
# MAGIC
# MAGIC > **Genie → „Co říkají naše data?“**  
# MAGIC > **Knowledge Assistant → „Co říkají naše dokumenty?“**
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 📁 Odkud Knowledge Assistant získává znalosti?
# MAGIC
# MAGIC Pro náš workshop už máme připravený Knowledge Assistant:
# MAGIC
# MAGIC **`agent-bricks-ws-saldo-docs`**
# MAGIC
# MAGIC Jeho zdrojem jsou dokumenty uložené ve **Volume**.
# MAGIC
# MAGIC 💡 **Volume** si pro tuto chvíli můžeme představit jednoduše jako místo v Databricks, kam ukládáme soubory — například `.md`, `.pdf` nebo další dokumenty.
# MAGIC
# MAGIC Knowledge Assistant nad tímto obsahem umožňuje vyhledávat relevantní informace a používat je při tvorbě odpovědi.
# MAGIC
# MAGIC > 🔎 **Tip:** Než Knowledge Assistant připojíte k Supervisorovi, můžete si jej otevřít v Agent Bricks a podívat se, jaké zdroje a instrukce má nakonfigurované.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 👣 Připojíme Knowledge Assistant
# MAGIC
# MAGIC Vraťte se do svého **Supervisor Agenta**.
# MAGIC
# MAGIC V části **Tools and sub-agents**:
# MAGIC
# MAGIC 1. Klikněte na **Add a Knowledge Assistant**
# MAGIC 2. Vyhledejte `agent-bricks-ws-saldo-docs`
# MAGIC 3. Vyberte jej a přidejte k Supervisorovi
# MAGIC
# MAGIC Náš Supervisor nyní dokáže kombinovat:
# MAGIC
# MAGIC 📊 **fakta ze strukturovaných dat** → Genie Agents  
# MAGIC 📄 **znalosti z dokumentů** → Knowledge Assistant
# MAGIC
# MAGIC > 🧭 **Kontrola**
# MAGIC >
# MAGIC > V části **Tools and sub-agents** byste nyní měli mít:
# MAGIC >
# MAGIC > - 💰 Saldo payroll operations
# MAGIC > - 🏥 Saldo platform health
# MAGIC > - 📚 agent-bricks-ws-saldo-docs

# COMMAND ----------

# MAGIC %md
# MAGIC ## ⚙️ Jak Knowledge Assistant funguje na pozadí
# MAGIC
# MAGIC Knowledge Assistant při každé otázce **nečte celou smlouvu od začátku**.
# MAGIC
# MAGIC Používá princip **RAG — Retrieval-Augmented Generation**:
# MAGIC
# MAGIC > 🔎 **Retrieval** → najdi v dokumentech relevantní znalost  
# MAGIC > 🧠 **Generation** → dej ji LLM jako kontext a vytvoř odpověď
# MAGIC
# MAGIC Podívejme se, co se přibližně stane s naším dokumentem  
# MAGIC 📄 **Subscription Agreement – Alpine Retail**.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 1️⃣ ✂️ Dokument rozdělíme na menší části — *chunky*
# MAGIC
# MAGIC Dlouhou smlouvu nechceme při každé otázce posílat celou do LLM.
# MAGIC
# MAGIC Rozdělíme ji na menší významové části:
# MAGIC
# MAGIC ```text
# MAGIC 📄 Subscription Agreement – Alpine Retail
# MAGIC
# MAGIC         │
# MAGIC         ├── 🧩 CHUNK A
# MAGIC         │   "This agreement runs for 36 months..."
# MAGIC         │
# MAGIC         │   📌 Term and Renewal
# MAGIC         │
# MAGIC         ├── 🧩 CHUNK B
# MAGIC         │   "Alpine Retail pays a monthly subscription..."
# MAGIC         │
# MAGIC         │   📌 Fees and Payment
# MAGIC         │
# MAGIC         ├── 🧩 CHUNK C
# MAGIC         │   "Where Saldo fails to meet the 99.9% availability
# MAGIC         │    target, Alpine Retail may claim a service credit..."
# MAGIC         │
# MAGIC         │   📌 Service Levels
# MAGIC         │
# MAGIC         ├── 🧩 CHUNK D
# MAGIC         │   "Payments rejected because submitted data did not
# MAGIC         │    meet Saldo's specification do not give rise to
# MAGIC         │    a service credit."
# MAGIC         │
# MAGIC         │   📌 Service Levels
# MAGIC         │
# MAGIC         └── 🧩 CHUNK E
# MAGIC             "Alpine Retail receives Professional support..."
# MAGIC
# MAGIC             📌 Support
# MAGIC ```
# MAGIC
# MAGIC 💡 **Chunk = malý kus dokumentu, se kterým můžeme samostatně pracovat.**
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 2️⃣ 🧠 Z chunků vytvoříme vektorovou reprezentaci
# MAGIC
# MAGIC Význam každého chunku lze pomocí **embedding modelu** převést na čísla:
# MAGIC
# MAGIC ```text
# MAGIC 🧩 "agreement runs for 36 months..."
# MAGIC              ↓
# MAGIC          🧠 embedding
# MAGIC              ↓
# MAGIC 🔢 [0.12, 0.81, -0.34, ...]
# MAGIC
# MAGIC
# MAGIC 🧩 "rejected payments do not give rise
# MAGIC     to a service credit..."
# MAGIC              ↓
# MAGIC          🧠 embedding
# MAGIC              ↓
# MAGIC 🔢 [0.73, -0.21, 0.64, ...]
# MAGIC ```
# MAGIC
# MAGIC ⚠️ Konkrétní čísla nejsou důležitá.
# MAGIC
# MAGIC Důležité je, že vektory zachycují **význam textu**.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 3️⃣ ❓ Přijde otázka uživatele
# MAGIC
# MAGIC Support specialista se zeptá:
# MAGIC
# MAGIC > **„Má Alpine Retail nárok na kompenzaci za zaměstnance odmítnuté při payroll runu?“**
# MAGIC
# MAGIC Otázku převedeme stejným způsobem:
# MAGIC
# MAGIC ```text
# MAGIC ❓ "nárok na kompenzaci za odmítnutý payroll"
# MAGIC                     ↓
# MAGIC                 🧠 embedding
# MAGIC                     ↓
# MAGIC              🔢 [0.69, -0.18, 0.61, ...]
# MAGIC ```
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 4️⃣ 🔎 Najdeme významově nejbližší části smlouvy
# MAGIC
# MAGIC Porovnáme význam otázky s jednotlivými chunky:
# MAGIC
# MAGIC ```text
# MAGIC                          ❓
# MAGIC         "kompenzace za odmítnutý payroll"
# MAGIC                          │
# MAGIC                          ▼
# MAGIC
# MAGIC  🧩 Term       🧩 Fees       🧩 SLA       🧩 Rejected payments
# MAGIC     │              │             │                 │
# MAGIC    12 %           34 %          76 %             ⭐ 96 %
# MAGIC                                                    │
# MAGIC                                                    ▼
# MAGIC                                               🎯 MATCH
# MAGIC ```
# MAGIC
# MAGIC A právě tady je kouzlo semantic search. ✨
# MAGIC
# MAGIC Uživatel napsal:
# MAGIC
# MAGIC > **„nárok na kompenzaci“**
# MAGIC
# MAGIC ale dokument říká:
# MAGIC
# MAGIC > **„give rise to a service credit“**
# MAGIC
# MAGIC 🔎 Nemusíme hledat stejná slova.  
# MAGIC **Hledáme podobný význam.**
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 5️⃣ 📚 Relevantní části přidáme k otázce jako kontext
# MAGIC
# MAGIC Knowledge Assistant vezme například tyto nalezené části:
# MAGIC
# MAGIC ```text
# MAGIC 📚 KONTEXT ZE SMLOUVY
# MAGIC
# MAGIC "Where Saldo fails to meet the availability target,
# MAGIC Alpine Retail may claim a service credit..."
# MAGIC
# MAGIC +
# MAGIC
# MAGIC "Payments rejected because submitted data did not meet
# MAGIC Saldo's specification ... do not give rise to a service credit."
# MAGIC ```
# MAGIC
# MAGIC a spolu s původní otázkou je předá LLM:
# MAGIC
# MAGIC ```text
# MAGIC        ❓ otázka
# MAGIC            +
# MAGIC    📚 nalezený kontext
# MAGIC            │
# MAGIC            ▼
# MAGIC          🧠 LLM
# MAGIC            │
# MAGIC            ▼
# MAGIC         💬 odpověď
# MAGIC ```
# MAGIC
# MAGIC LLM pak může dojít například k odpovědi:
# MAGIC
# MAGIC > 💬 **Ne. Pokud byli zaměstnanci odmítnuti proto, že vstupní data nesplňovala specifikaci Saldo, smlouva takový případ nepovažuje za nedostupnost služby a Alpine Retail nemá nárok na service credit.**
# MAGIC
# MAGIC

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🔎 Krok 4 — Najdeme podobné historické případy
# MAGIC
# MAGIC Při vyšetřování incidentu je často velmi užitečná otázka:
# MAGIC
# MAGIC > **„Řešili jsme už někdy něco podobného?“**
# MAGIC
# MAGIC Saldo má historii předchozích support případů a poznámek k jejich řešení.
# MAGIC
# MAGIC Mohli bychom samozřejmě hledat podle konkrétního čísla případu, zákazníka nebo chybového kódu.
# MAGIC
# MAGIC Často ale přesně nevíme, **co hledáme**.
# MAGIC
# MAGIC Například:
# MAGIC
# MAGIC > „Najdi podobné případy, kdy po změně systému přestala části zaměstnanců procházet výplata.“
# MAGIC
# MAGIC Historický případ přitom nemusí obsahovat úplně stejná slova ani stejný error code.
# MAGIC
# MAGIC Potřebujeme hledat podle **významové podobnosti**.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🧠 Od klasického hledání k sémantickému hledání
# MAGIC
# MAGIC Představme si dva historické případy:
# MAGIC
# MAGIC **Case A**
# MAGIC
# MAGIC > „Employees rejected after payroll validation change.“
# MAGIC
# MAGIC **Case B**
# MAGIC
# MAGIC > „Workers missing from salary processing following platform update.“
# MAGIC
# MAGIC Text není stejný.
# MAGIC
# MAGIC Význam ale může být velmi podobný.
# MAGIC
# MAGIC Právě pro takové hledání můžeme použít **AI Search / Vector Search**.
# MAGIC
# MAGIC Jednoduše řečeno:
# MAGIC
# MAGIC > 🔤 **Klasické hledání** → hledá stejná slova nebo konkrétní hodnoty  
# MAGIC > 🧠 **Vector Search** → dokáže hledat obsah s podobným významem
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🔎 Co použijeme v našem workshopu?
# MAGIC
# MAGIC Pro historické support případy máme připravený AI Search index:
# MAGIC
# MAGIC **`case_notes_index`**
# MAGIC
# MAGIC Jeho úkolem je umožnit hledání nad historickými poznámkami ze support případů.
# MAGIC
# MAGIC Princip je:
# MAGIC
# MAGIC **🎫 historické case notes → 🔎 AI Search index → 🧠 hledání podobných případů**
# MAGIC
# MAGIC Supervisor tak může při vyšetřování položit například otázku:
# MAGIC
# MAGIC > **„Najdi historické případy podobné současnému problému Alpine Retail.“**
# MAGIC
# MAGIC a získané zkušenosti použít jako další zdroj informací.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🛠️ Jak vznikl `case_notes_index`?
# MAGIC
# MAGIC AI Search index musí být vytvořen nad zdrojovými daty, která chceme prohledávat.
# MAGIC
# MAGIC Pro workshop jsme tuto technickou část připravili předem, abychom se mohli soustředit na návrh agentního systému.
# MAGIC
# MAGIC Náš připravený tok tedy vypadá přibližně takto:
# MAGIC
# MAGIC **historické support cases → case notes → `case_notes_index` → Supervisor**
# MAGIC
# MAGIC > 💡 V reálném projektu bychom stejným způsobem vytvořili vlastní index nad firemními daty, ve kterých potřebujeme vyhledávat podle významu.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 👣 Připojíme AI Search index
# MAGIC
# MAGIC Vraťte se do svého **Supervisor Agenta**.
# MAGIC
# MAGIC V části **Tools and sub-agents**:
# MAGIC
# MAGIC 1. Klikněte na **Add an AI Search index**
# MAGIC 2. Vyhledejte `case_notes_index`
# MAGIC 3. Vyberte jej a přidejte k Supervisorovi
# MAGIC
# MAGIC Supervisor nyní získal další typ specializovaného nástroje:
# MAGIC
# MAGIC 📊 **strukturovaná data** → Genie Agents  
# MAGIC 📄 **dokumentace** → Knowledge Assistant  
# MAGIC 🔎 **podobné historické případy** → AI Search
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC > 🧭 **Kontrola**
# MAGIC >
# MAGIC > V části **Tools and sub-agents** byste nyní měli mít:
# MAGIC >
# MAGIC > - 💰 Saldo payroll operations
# MAGIC > - 🏥 Saldo platform health
# MAGIC > - 📚 agent-bricks-ws-saldo-docs
# MAGIC > - 🔎 case_notes_index

# COMMAND ----------

# MAGIC %md
# MAGIC ## ⚙️ Co se děje na pozadí?
# MAGIC
# MAGIC Princip už vlastně známe z **Knowledge Assistant**. 🧠
# MAGIC
# MAGIC I tady využíváme **vektorovou reprezentaci a sémantickou podobnost**.
# MAGIC
# MAGIC Rozdíl je hlavně v tom, **co prohledáváme**:
# MAGIC
# MAGIC ```text
# MAGIC 📚 Knowledge Assistant
# MAGIC dokumenty → ✂️ chunky → 🧠 vektory → 🔎 relevantní části dokumentů
# MAGIC
# MAGIC
# MAGIC 🔎 AI Search
# MAGIC historické case notes → 🧠 vektory → 🔎 významově podobné případy
# MAGIC ```
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🎫 Příklad z našeho incidentu
# MAGIC
# MAGIC Supervisor už ví, že:
# MAGIC
# MAGIC > **47 zaměstnanců Alpine Retail bylo odmítnuto kvůli validaci bankovních údajů.**
# MAGIC
# MAGIC Nemusí tedy znát ID historického ticketu ani přesný error code.
# MAGIC
# MAGIC Vytvoří vyhledávací dotaz například ve významu:
# MAGIC
# MAGIC > 🔍 *„Najdi případy, kdy byla část zaměstnanců odmítnuta při payrollu kvůli validaci platebních údajů.“*
# MAGIC
# MAGIC AI Search tento dotaz porovná s vektorovou reprezentací historických case notes:
# MAGIC
# MAGIC ```text
# MAGIC                          🔍 SOUČASNÝ PROBLÉM
# MAGIC                 rejected employees / payroll /
# MAGIC                    bank account validation
# MAGIC                               │
# MAGIC                               ▼
# MAGIC                        🧠 embedding
# MAGIC                               │
# MAGIC                               ▼
# MAGIC                     🔎 VECTOR SEARCH
# MAGIC                               │
# MAGIC              ┌────────────────┼────────────────┐
# MAGIC              ▼                ▼                ▼
# MAGIC          🎫 Case A         🎫 Case B        🎫 Case C
# MAGIC         similarity        similarity       similarity
# MAGIC            0.91              0.84             0.31
# MAGIC              │                │
# MAGIC              └───────┬────────┘
# MAGIC                      ▼
# MAGIC              🎯 podobné případy
# MAGIC                      │
# MAGIC                      ▼
# MAGIC                 🧠 Supervisor
# MAGIC ```
# MAGIC
# MAGIC 💡 **Nemusí se shodovat slova. Musí být podobný význam.**
# MAGIC
# MAGIC Historický case může například říkat:
# MAGIC
# MAGIC > *“Workers missing from salary processing after payment validation update.”*
# MAGIC
# MAGIC a přesto může být velmi relevantní k našemu:
# MAGIC
# MAGIC > *“47 employees rejected from payroll due to invalid bank account data.”*
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🧩 Jak to zapadá do našeho systému?
# MAGIC
# MAGIC Supervisor teď získává další schopnost:
# MAGIC
# MAGIC **Genie** → 📊 *Co se stalo?*  
# MAGIC **Knowledge Assistant** → 📚 *Co o tom říká dokumentace?*  
# MAGIC **AI Search** → 🔎 *Řešili jsme už někdy něco podobného?*
# MAGIC
# MAGIC > 🎯 **Supervisor nemusí vědět, kde odpověď je. Vybere správného specialistu podle typu otázky.**

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🧮 Krok 5 — Přidáme přesný business výpočet
# MAGIC
# MAGIC Doteď Supervisor používal nástroje především k **hledání informací**.
# MAGIC
# MAGIC Některé úlohy ale nechceme nechat počítat jazykový model.
# MAGIC
# MAGIC Představme si například, že při incidentu potřebujeme určit:
# MAGIC
# MAGIC > **„Na jaký SLA kredit má zákazník nárok?“**
# MAGIC
# MAGIC Výsledek může záviset na přesných business pravidlech — například závažnosti incidentu, délce výpadku nebo měsíčním poplatku zákazníka.
# MAGIC
# MAGIC Takový výpočet chceme mít:
# MAGIC
# MAGIC - 🎯 přesný,
# MAGIC - 🔁 opakovatelný,
# MAGIC - 🔍 auditovatelný,
# MAGIC - 🧪 samostatně testovatelný.
# MAGIC
# MAGIC Proto jej implementujeme jako **funkci** a Supervisor ji pouze zavolá se správnými vstupy.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### ⚙️ UC Function
# MAGIC
# MAGIC V Databricks můžeme pro takové operace použít **Unity Catalog Function (UC Function)**.
# MAGIC
# MAGIC Pro náš workshop máme připravenou funkci:
# MAGIC
# MAGIC **`calculate_sla_credit`**
# MAGIC
# MAGIC Její role je jednoduchá:
# MAGIC
# MAGIC **Supervisor zjistí potřebná fakta → předá je funkci → funkce provede výpočet → Supervisor použije výsledek**
# MAGIC
# MAGIC Například:
# MAGIC
# MAGIC **🏥 incident data + 💰 zákaznická data → 🧮 `calculate_sla_credit` → výše SLA kreditu**
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 💡 Proč výpočet jednoduše neudělá LLM?
# MAGIC
# MAGIC Tohle je důležitý princip při návrhu agentních systémů.
# MAGIC
# MAGIC > **LLM nemusí dělat všechno.**
# MAGIC
# MAGIC LLM je velmi dobrý v pochopení úkolu, práci s jazykem, hledání souvislostí a rozhodování, **který nástroj použít**.
# MAGIC
# MAGIC Přesná business logika ale často patří do klasického kódu.
# MAGIC
# MAGIC Supervisor tedy nemusí znát vzorec pro výpočet SLA kreditu.
# MAGIC
# MAGIC Potřebuje pouze vědět:
# MAGIC
# MAGIC > **„Když potřebuji spočítat SLA kredit, mám k dispozici nástroj `calculate_sla_credit`.“**
# MAGIC
# MAGIC Samotný výpočet provede funkce.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 👣 Připojíme UC Function
# MAGIC
# MAGIC Vraťte se do svého **Supervisor Agenta**.
# MAGIC
# MAGIC V části **Tools and sub-agents**:
# MAGIC
# MAGIC 1. Klikněte na **Add a UC Function**
# MAGIC 2. Vyhledejte `calculate_sla_credit`
# MAGIC 3. Vyberte funkci a přidejte ji k Supervisorovi
# MAGIC
# MAGIC Supervisor nyní dokáže nejen získávat informace, ale také použít **deterministickou business logiku**.
# MAGIC
# MAGIC 📊 **strukturovaná data** → Genie Agents  
# MAGIC 📄 **dokumentace** → Knowledge Assistant  
# MAGIC 🔎 **podobné historické případy** → AI Search  
# MAGIC 🧮 **business logika a výpočty** → UC Function
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC > 🧭 **Kontrola**
# MAGIC >
# MAGIC > V části **Tools and sub-agents** byste nyní měli mít:
# MAGIC >
# MAGIC > - 💰 Saldo payroll operations
# MAGIC > - 🏥 Saldo platform health
# MAGIC > - 📚 agent-bricks-ws-saldo-docs
# MAGIC > - 🔎 case_notes_index
# MAGIC > - 🧮 calculate_sla_credit
# MAGIC >
# MAGIC > Náš Supervisor už tedy umí **hledat, číst, porovnávat a počítat**.
# MAGIC >
# MAGIC > V dalších krocích mu přidáme ještě jednu zásadní schopnost: **pracovat s dalšími systémy a provádět akce**.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 📧 Krok 6 — Připojíme komunikaci se zákazníkem
# MAGIC
# MAGIC Doteď jsme pracovali především s informacemi, které máme uvnitř Salda.
# MAGIC
# MAGIC Při řešení skutečného support incidentu ale potřebujeme znát také **komunikaci se zákazníkem**.
# MAGIC
# MAGIC Může nás například zajímat:
# MAGIC
# MAGIC - 📩 co přesně zákazník nahlásil,
# MAGIC - 📩 zda jsme ho na problém nebo změnu upozornili,
# MAGIC - 📩 jaké informace jsme mu už poslali,
# MAGIC - ✉️ případně připravit další odpověď.
# MAGIC
# MAGIC V našem scénáři tuto schopnost reprezentuje **Outlook**.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🔌 Připojujeme další systém
# MAGIC
# MAGIC Tady se dostáváme k další důležité vlastnosti Supervisora.
# MAGIC
# MAGIC Nemusí pracovat pouze s daty a agenty uvnitř Databricks.
# MAGIC
# MAGIC Můžeme mu zpřístupnit také **další aplikace a služby**, které jsou součástí reálného business procesu.
# MAGIC
# MAGIC Princip je:
# MAGIC
# MAGIC **📧 Outlook → nástroj / integrace → 🧠 Supervisor**
# MAGIC
# MAGIC Supervisor pak může komunikaci použít jako další zdroj při vyšetřování incidentu.
# MAGIC
# MAGIC Například může zjistit:
# MAGIC
# MAGIC > **„Byl Alpine Retail před změnou validace bankovních účtů upozorněn?“**
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 👀 Čtení vs. provedení akce
# MAGIC
# MAGIC U externích systémů se ale objevuje důležitý rozdíl.
# MAGIC
# MAGIC Supervisor může například:
# MAGIC
# MAGIC **READ**
# MAGIC
# MAGIC > 📖 přečíst předchozí komunikaci se zákazníkem
# MAGIC
# MAGIC ale může také dostat možnost:
# MAGIC
# MAGIC **WRITE / ACT**
# MAGIC
# MAGIC > ✉️ připravit nebo odeslat novou odpověď
# MAGIC
# MAGIC To už není pouze získávání informací.
# MAGIC
# MAGIC Agent začíná **provádět akce v jiném systému**.
# MAGIC
# MAGIC A právě u takových operací musíme přemýšlet také o:
# MAGIC
# MAGIC - 🔐 oprávněních,
# MAGIC - 👤 identitě uživatele,
# MAGIC - 🛡️ bezpečnosti,
# MAGIC - ✋ případném schválení člověkem před provedením akce.
# MAGIC
# MAGIC K tématu **human approval** se ještě vrátíme.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 👣 Připojíme Outlook
# MAGIC
# MAGIC Pro workshop máme potřebnou integraci připravenou předem.
# MAGIC
# MAGIC V části **Tools and sub-agents** vyhledejte připravený nástroj pro práci s Outlookem a přidejte jej k Supervisorovi.
# MAGIC
# MAGIC > 💡 Konkrétní technický způsob připojení externí aplikace se může lišit podle použité integrace. Pro tento workshop používáme předpřipravenou demo konfiguraci.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC Náš Supervisor nyní získává další typ schopnosti:
# MAGIC
# MAGIC 📊 **strukturovaná data** → Genie Agents  
# MAGIC 📄 **dokumentace** → Knowledge Assistant  
# MAGIC 🔎 **podobné historické případy** → AI Search  
# MAGIC 🧮 **business logika** → UC Function  
# MAGIC 📧 **komunikace a externí systém** → Outlook
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC > 🧭 **Kontrola**
# MAGIC >
# MAGIC > V části **Tools and sub-agents** byste nyní měli mít také připravený Outlook nástroj.
# MAGIC >
# MAGIC > Supervisor už tedy nemusí pouze analyzovat interní data. Dokáže do vyšetřování zapojit také **kontext z komunikace se zákazníkem**.
# MAGIC >
# MAGIC > Zbývá nám poslední důležitá část našeho support procesu: **samotný support case**.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🎫 Krok 7 — Připojíme support systém CaseHub
# MAGIC
# MAGIC Máme informace o payrollu, platformě, dokumentaci, historických případech i komunikaci se zákazníkem.
# MAGIC
# MAGIC Samotný incident ale support tým spravuje v **ticketovacím systému**.
# MAGIC
# MAGIC V našem scénáři tuto roli představuje **CaseHub**.
# MAGIC
# MAGIC CaseHub obsahuje aktuální stav support případů, například:
# MAGIC
# MAGIC - 🎫 identifikátor a popis případu,
# MAGIC - 🚨 severity,
# MAGIC - 👤 komu je případ přiřazen,
# MAGIC - 🔗 vazbu na payroll run nebo incident,
# MAGIC - 📌 aktuální status,
# MAGIC - 📝 informace vznikající během řešení.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🧠 Proč CaseHub připojujeme k Supervisorovi?
# MAGIC
# MAGIC Představme si, že uživatel zadá:
# MAGIC
# MAGIC > **„Vyšetři incident Alpine Retail.“**
# MAGIC
# MAGIC Supervisor může nejprve zjistit, **který support case se incidentu týká**, a potom použít jeho informace při dalším vyšetřování.
# MAGIC
# MAGIC Tím ale možnosti nekončí.
# MAGIC
# MAGIC Po dokončení vyšetřování může vzniknout požadavek například:
# MAGIC
# MAGIC > **„Aktualizuj support case výsledkem vyšetřování.“**
# MAGIC
# MAGIC A tady se dostáváme od **analýzy** k **akci**.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 👀 READ vs. ✍️ WRITE
# MAGIC
# MAGIC CaseHub může Supervisorovi nabídnout dva typy operací:
# MAGIC
# MAGIC **👀 READ**
# MAGIC
# MAGIC Přečíst aktuální stav support případu.
# MAGIC
# MAGIC Například:
# MAGIC
# MAGIC > „Najdi otevřený case Alpine Retail.“
# MAGIC
# MAGIC **✍️ WRITE**
# MAGIC
# MAGIC Provést změnu v support systému.
# MAGIC
# MAGIC Například:
# MAGIC
# MAGIC > „Změň severity případu.“  
# MAGIC > „Přiřaď případ jinému člověku.“  
# MAGIC > „Aktualizuj status případu.“
# MAGIC
# MAGIC To je zásadní rozdíl.
# MAGIC
# MAGIC ```text
# MAGIC READ
# MAGIC 🧠 Supervisor → 🎫 CaseHub → získání informace
# MAGIC
# MAGIC WRITE
# MAGIC 🧠 Supervisor → 🎫 CaseHub → změna stavu systému

# COMMAND ----------

# MAGIC %md
# MAGIC ## 📝 Krok 8 — Naučíme Supervisora, jak má pracovat
# MAGIC
# MAGIC Máme připravené všechny specialisty a nástroje.
# MAGIC
# MAGIC Samotné připojení nástrojů ale ještě nestačí.
# MAGIC
# MAGIC Supervisor potřebuje rozumět:
# MAGIC
# MAGIC - 🎯 jakou roli má plnit,
# MAGIC - 🧰 k čemu jednotlivé nástroje slouží,
# MAGIC - 🧭 jak má postupovat při řešení komplexního úkolu,
# MAGIC - 🔎 kdy má hledat další informace,
# MAGIC - 🛑 kdy už má dostatek důkazů a má formulovat závěr,
# MAGIC - ✋ jak zacházet s akcemi, které mohou vyžadovat schválení.
# MAGIC
# MAGIC K tomu slouží **Instructions**.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🧠 Tools vs. Instructions
# MAGIC
# MAGIC Je důležité rozlišovat dvě věci:
# MAGIC
# MAGIC **Tools and sub-agents**
# MAGIC
# MAGIC > **Co má Supervisor k dispozici?**
# MAGIC
# MAGIC **Instructions**
# MAGIC
# MAGIC > **Jak a kdy má dostupné nástroje používat?**
# MAGIC
# MAGIC Můžeme mít perfektně připravené specialisty, ale pokud Supervisor neví, k čemu jsou určeni, bude jejich orchestrace nespolehlivá.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### ✍️ Nastavíme Instructions
# MAGIC
# MAGIC Do pole **Instructions** vložte:
# MAGIC
# MAGIC ~~~text
# MAGIC You are a support investigation supervisor for Saldo, a payroll SaaS platform.
# MAGIC
# MAGIC Your job is to investigate customer support issues by coordinating the available specialist agents and tools.
# MAGIC
# MAGIC Use the available capabilities according to their purpose:
# MAGIC
# MAGIC - Saldo payroll operations: customer, employee and payroll data, payroll runs, rejected employees, rejection reasons, bank account data and cost centres.
# MAGIC - Saldo platform health: platform incidents, releases, deployments, changes and operational events.
# MAGIC - Saldo docs Knowledge Assistant: product documentation, policies, contracts and other Saldo documents.
# MAGIC - case_notes_index: search historical support cases and case notes for similar previous issues.
# MAGIC - calculate_sla_credit: calculate an SLA credit when the required inputs are known.
# MAGIC - Outlook: inspect relevant customer communication and prepare communication when appropriate.
# MAGIC - CaseHub: inspect and work with support cases.
# MAGIC
# MAGIC When investigating a complex issue:
# MAGIC
# MAGIC 1. First understand the customer issue and determine what information is needed.
# MAGIC 2. Use the relevant specialist agents and tools. Do not rely on a single source when the task requires multiple domains.
# MAGIC 3. Correlate findings across sources, especially dates, error codes, releases, platform changes and historical cases.
# MAGIC 4. Clearly distinguish observed facts from inferred or likely causes.
# MAGIC 5. Do not invent information that is not supported by the available agents or tools.
# MAGIC 6. If information is missing, state what is missing instead of guessing.
# MAGIC 7. Use actions that modify external systems only when they are necessary for the requested task.
# MAGIC 8. If an action requires user approval, request approval before performing it.
# MAGIC
# MAGIC For incident investigations, provide a concise final summary containing:
# MAGIC - what happened,
# MAGIC - affected scope,
# MAGIC - root cause or most likely cause,
# MAGIC - supporting evidence,
# MAGIC - recommended next actions.
# MAGIC ~~~
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 💡 Co je na těchto Instructions důležité?
# MAGIC
# MAGIC Všimněte si, že Supervisorovi **nevysvětlujeme detailně payroll, IBAN ani konkrétní incident Alpine Retail**.
# MAGIC
# MAGIC Tyto znalosti patří jednotlivým specialistům.
# MAGIC
# MAGIC Supervisor potřebuje především vědět:
# MAGIC
# MAGIC > **Kdo co umí a kdy ho mám použít?**
# MAGIC
# MAGIC Například:
# MAGIC
# MAGIC **„Kolik zaměstnanců bylo zamítnuto?“**  
# MAGIC → 💰 Payroll Genie
# MAGIC
# MAGIC **„Proběhla v té době nějaká změna platformy?“**  
# MAGIC → 🏥 Platform Health Genie
# MAGIC
# MAGIC **„Co k této chybě říká dokumentace?“**  
# MAGIC → 📚 Knowledge Assistant
# MAGIC
# MAGIC **„Řešili jsme už něco podobného?“**  
# MAGIC → 🔎 AI Search
# MAGIC
# MAGIC **„Spočítej případný SLA kredit.“**  
# MAGIC → 🧮 UC Function
# MAGIC
# MAGIC Supervisor tedy není další databází znalostí.
# MAGIC
# MAGIC Je především **orchestrátorem dostupných specialistů a nástrojů**.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🎯 Description
# MAGIC
# MAGIC Do pole **Description** můžeme použít například:
# MAGIC
# MAGIC ~~~text
# MAGIC Investigates Saldo customer and payroll incidents by coordinating specialized agents and tools.
# MAGIC ~~~
# MAGIC
# MAGIC Description stručně říká, **k čemu celý Supervisor slouží**.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC > 🧭 **Kontrola**
# MAGIC >
# MAGIC > Máme nyní:
# MAGIC >
# MAGIC > **specializované agenty + nástroje + instrukce pro jejich orchestraci**
# MAGIC >
# MAGIC > Supervisor je připravený.
# MAGIC >
# MAGIC > V dalším kroku mu poprvé nezadáme dílčí otázku pro konkrétního specialistu.
# MAGIC >
# MAGIC > Zadáme mu **celý business problém** a necháme ho rozhodnout, jak jej vyřešit.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🚀 Krok 9 — Necháme Supervisora vyšetřit celý incident
# MAGIC
# MAGIC Doteď jsme jednotlivým specialistům zadávali poměrně konkrétní otázky.
# MAGIC
# MAGIC Například:
# MAGIC
# MAGIC > „Kolik zaměstnanců bylo zamítnuto?“
# MAGIC
# MAGIC nebo:
# MAGIC
# MAGIC > „Došlo v poslední době ke změně validace bankovních účtů?“
# MAGIC
# MAGIC Tím jsme ale část orchestrace stále prováděli **my sami**.
# MAGIC
# MAGIC My jsme rozhodovali:
# MAGIC
# MAGIC **koho se zeptat → na co se zeptat → jak výsledky spojit**
# MAGIC
# MAGIC Teď to změníme.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🎯 Zadáme business problém, ne postup
# MAGIC
# MAGIC Supervisorovi neřekneme:
# MAGIC
# MAGIC > „Nejdřív zavolej Payroll Genie, potom Platform Health Genie a nakonec prohledej dokumentaci.“
# MAGIC
# MAGIC Místo toho mu popíšeme **cíl vyšetřování**.
# MAGIC
# MAGIC Do testovacího chatu Supervisora vložte:
# MAGIC
# MAGIC ~~~text
# MAGIC Vyšetři incident Alpine Retail, při kterém 47 zaměstnanců nedostalo výplatu.
# MAGIC
# MAGIC Zjisti, co se stalo, jaká je pravděpodobná příčina a zda problém souvisí s nějakou nedávnou změnou platformy.
# MAGIC
# MAGIC Prověř také, zda jsme podobný problém řešili v minulosti a co k řešení říká dostupná dokumentace.
# MAGIC
# MAGIC Nakonec navrhni další postup.
# MAGIC ~~~
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 👀 Nesledujte jen výslednou odpověď
# MAGIC
# MAGIC Pro tuto část workshopu je možná ještě zajímavější sledovat **cestu k odpovědi**.
# MAGIC
# MAGIC V průběhu vyšetřování si všímejte:
# MAGIC
# MAGIC - 🧠 Jak Supervisor rozdělil problém na menší části?
# MAGIC - 🧰 Které specialisty a nástroje se rozhodl použít?
# MAGIC - ❓ Jaké otázky jim sám vytvořil?
# MAGIC - 🔄 Použil výsledek jednoho kroku jako vstup pro další?
# MAGIC - 🚫 Které dostupné nástroje naopak nepoužil?
# MAGIC - 🧩 Jak spojil informace z různých zdrojů do jednoho závěru?
# MAGIC
# MAGIC Supervisor má k dispozici více nástrojů, ale **nemusí použít všechny**.
# MAGIC
# MAGIC To je důležité.
# MAGIC
# MAGIC > 💡 Cílem orchestrace není spustit všechny dostupné nástroje.
# MAGIC >
# MAGIC > Cílem je vybrat **správné nástroje pro konkrétní úkol**.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🔎 Co bychom měli přibližně pozorovat?
# MAGIC
# MAGIC Přesný postup nemusí být při každém spuštění totožný.
# MAGIC
# MAGIC Typické vyšetřování ale může vypadat například takto:
# MAGIC
# MAGIC **💰 Payroll Genie**  
# MAGIC → najde problematický payroll run  
# MAGIC → zjistí 47 zamítnutých zaměstnanců  
# MAGIC → dohledá důvod zamítnutí
# MAGIC
# MAGIC ⬇️
# MAGIC
# MAGIC **🏥 Platform Health Genie**  
# MAGIC → prověří incidenty, releasy a změny platformy  
# MAGIC → hledá možnou souvislost s problémem
# MAGIC
# MAGIC ⬇️
# MAGIC
# MAGIC **🔎 AI Search**  
# MAGIC → hledá podobné historické support případy
# MAGIC
# MAGIC ⬇️
# MAGIC
# MAGIC **📚 Knowledge Assistant**  
# MAGIC → ověří, co k problému a jeho řešení říká dokumentace
# MAGIC
# MAGIC ⬇️
# MAGIC
# MAGIC **🧠 Supervisor**  
# MAGIC → porovná získané informace  
# MAGIC → oddělí fakta od předpokladů  
# MAGIC → sestaví závěr a doporučený další postup
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 💡 A právě tady je rozdíl
# MAGIC
# MAGIC Na začátku workshopu jsme incident vyšetřovali takto:
# MAGIC
# MAGIC **👤 člověk → 💰 Genie → 👤 člověk → 🏥 Genie → 👤 člověk → spojení výsledků**
# MAGIC
# MAGIC Teď máme:
# MAGIC
# MAGIC **👤 člověk → 🧠 Supervisor → specialisté a nástroje → výsledná odpověď**
# MAGIC
# MAGIC Člověk stále definuje **cíl**.
# MAGIC
# MAGIC Nemusí ale ručně řídit každý jednotlivý krok vyšetřování.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC > 🧭 **Pokud vyšetřování trvá příliš dlouho**
# MAGIC >
# MAGIC > Supervisor může při komplexním úkolu pokračovat v dalším dohledávání informací, i když už má pro odpověď dostatek podkladů.
# MAGIC >
# MAGIC > To není jen otázka modelu — je to také otázka **designu Instructions**.
# MAGIC >
# MAGIC > Při ladění produkčního agenta bychom například mohli doplnit pravidlo:
# MAGIC >
# MAGIC > *Use the minimum number of tool calls necessary to answer the request. Once sufficient evidence has been gathered, stop investigating and provide the final answer.*
# MAGIC >
# MAGIC > Návrh agentního systému proto nekončí jeho prvním funkčním spuštěním. **Instructions, nástroje a jejich popisy průběžně testujeme a ladíme podle skutečného chování.**

# COMMAND ----------

# MAGIC %md
# MAGIC ## ⚡ Krok 10 — Od analýzy k akci
# MAGIC
# MAGIC V předchozím kroku Supervisor incident **vyšetřil**.
# MAGIC
# MAGIC Dokázal si sám vybrat vhodné specialisty, získat informace z několika různých zdrojů a sestavit z nich závěr.
# MAGIC
# MAGIC Tím ale práce support týmu obvykle nekončí.
# MAGIC
# MAGIC Po zjištění příčiny incidentu může být potřeba například:
# MAGIC
# MAGIC - 🧮 spočítat případný SLA kredit,
# MAGIC - 🎫 aktualizovat support case,
# MAGIC - ✉️ připravit odpověď zákazníkovi,
# MAGIC - 👤 předat některé kroky ke schválení člověku.
# MAGIC
# MAGIC Tím se dostáváme od:
# MAGIC
# MAGIC > 🔎 **„Zjisti, co se stalo.“**
# MAGIC
# MAGIC k:
# MAGIC
# MAGIC > ⚡ **„Zjisti, co se stalo, a pomoz problém vyřešit.“**
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🧠 Supervisor už má potřebné nástroje
# MAGIC
# MAGIC Právě proto jsme mu v předchozích krocích přidali také:
# MAGIC
# MAGIC **🧮 `calculate_sla_credit`**  
# MAGIC → deterministický výpočet podle business pravidel
# MAGIC
# MAGIC **📧 Outlook**  
# MAGIC → práce s komunikací se zákazníkem
# MAGIC
# MAGIC **🎫 CaseHub**  
# MAGIC → práce se support případem
# MAGIC
# MAGIC Tentokrát tedy Supervisor nebude pouze získávat informace.
# MAGIC
# MAGIC Některé nástroje může použít také k **provedení akce**.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🚀 Zadáme komplexnější úkol
# MAGIC
# MAGIC Do testovacího chatu Supervisora zadejte:
# MAGIC
# MAGIC ~~~text
# MAGIC Vyšetři incident Alpine Retail, při kterém 47 zaměstnanců nedostalo výplatu.
# MAGIC
# MAGIC Zjisti příčinu problému a ověř ji pomocí dostupných zdrojů.
# MAGIC
# MAGIC Pokud jsou k dispozici potřebné informace, spočítej případný SLA kredit.
# MAGIC
# MAGIC Připrav návrh odpovědi zákazníkovi se shrnutím problému a doporučeným řešením.
# MAGIC
# MAGIC Nakonec navrhni, jak by měl být aktualizován příslušný support case.
# MAGIC ~~~
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 👀 Tentokrát sledujte ještě jednu věc
# MAGIC
# MAGIC Při prvním vyšetřování nás zajímalo především:
# MAGIC
# MAGIC > **Kterého specialistu Supervisor použije?**
# MAGIC
# MAGIC Teď nás navíc zajímá:
# MAGIC
# MAGIC > **Kde končí získávání informací a kde začíná akce?**
# MAGIC
# MAGIC Můžeme například pozorovat tento tok:
# MAGIC
# MAGIC **💰 Payroll Genie**  
# MAGIC → zjistí dopad incidentu
# MAGIC
# MAGIC **🏥 Platform Health Genie**  
# MAGIC → prověří příčinu a související změny
# MAGIC
# MAGIC **📚 Knowledge Assistant + 🔎 AI Search**  
# MAGIC → doplní dokumentaci a zkušenosti z minulosti
# MAGIC
# MAGIC **🧮 UC Function**  
# MAGIC → provede přesný business výpočet
# MAGIC
# MAGIC **📧 Outlook**  
# MAGIC → připraví komunikaci zákazníkovi
# MAGIC
# MAGIC **🎫 CaseHub**  
# MAGIC → připraví nebo provede změnu support případu
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### ⚠️ Čtení dat a změna systému nejsou totéž
# MAGIC
# MAGIC Tady se dostáváme k velmi důležitému rozdílu.
# MAGIC
# MAGIC Supervisor může provádět operace typu:
# MAGIC
# MAGIC **👀 READ**
# MAGIC
# MAGIC > „Najdi poslední payroll run.“
# MAGIC
# MAGIC > „Přečti support case.“
# MAGIC
# MAGIC > „Najdi relevantní dokumentaci.“
# MAGIC
# MAGIC Tyto operace pouze získávají informace.
# MAGIC
# MAGIC Jiné operace ale mohou mít skutečný dopad:
# MAGIC
# MAGIC **✍️ WRITE / ACT**
# MAGIC
# MAGIC > „Aktualizuj support case.“
# MAGIC
# MAGIC > „Odešli odpověď zákazníkovi.“
# MAGIC
# MAGIC > „Změň stav případu.“
# MAGIC
# MAGIC Agent tedy už pouze **neodpovídá na otázky**.
# MAGIC
# MAGIC Může dostat možnost **jednat jménem uživatele v dalších systémech**.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## ✋ A právě tady potřebujeme kontrolu
# MAGIC
# MAGIC Ne každou akci chceme automaticky provést jen proto, že se pro ni agent rozhodl.
# MAGIC
# MAGIC U citlivějších operací můžeme mezi rozhodnutí agenta a skutečné provedení akce vložit **schválení člověkem — Human-in-the-loop**.
# MAGIC
# MAGIC Princip je:
# MAGIC
# MAGIC **🧠 Supervisor → navrhne akci → ✋ člověk ji schválí → ⚡ akce se provede**
# MAGIC
# MAGIC Pokud člověk akci zamítne, změna se neprovede.
# MAGIC
# MAGIC > 💡 **Autonomie nemusí znamenat ztrátu kontroly.**
# MAGIC >
# MAGIC > Agent může autonomně vyšetřovat, plánovat a připravovat další kroky, zatímco vybrané akce s reálným dopadem mohou zůstat pod kontrolou člověka.
# MAGIC
# MAGIC V následujícím kroku se podíváme právě na **approvals** a na to, jak můžeme určit hranici mezi autonomním rozhodováním agenta a lidskou kontrolou.

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✋ Krok 11 — Human-in-the-loop a schvalování akcí
# MAGIC
# MAGIC Jakmile agent dostane možnost **měnit stav dalších systémů**, musíme se rozhodnout, jak velkou autonomii mu chceme dát.
# MAGIC
# MAGIC Ne všechny operace totiž představují stejné riziko.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 👀 Některé operace pouze čtou
# MAGIC
# MAGIC Například:
# MAGIC
# MAGIC - zjistit stav payroll runu,
# MAGIC - přečíst support case,
# MAGIC - vyhledat informace v dokumentaci,
# MAGIC - najít podobný historický incident.
# MAGIC
# MAGIC Takové operace pouze získávají informace:
# MAGIC
# MAGIC **🧠 Supervisor → 🔎 nástroj → 📄 informace**
# MAGIC
# MAGIC Systém se jejich provedením nemění.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### ⚡ Jiné operace něco skutečně mění
# MAGIC
# MAGIC Například:
# MAGIC
# MAGIC - ✉️ odeslat e-mail zákazníkovi,
# MAGIC - 🎫 změnit stav support případu,
# MAGIC - 👤 změnit jeho přiřazení,
# MAGIC - 📝 zapsat výsledek vyšetřování do externího systému.
# MAGIC
# MAGIC Tady už agent provádí akci s reálným dopadem:
# MAGIC
# MAGIC **🧠 Supervisor → ⚡ nástroj → 🌍 změna systému**
# MAGIC
# MAGIC A právě zde může být vhodné vyžadovat **schválení člověkem**.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### ✋ Approval
# MAGIC
# MAGIC Místo okamžitého provedení citlivé akce může běh agenta vypadat například takto:
# MAGIC
# MAGIC **1️⃣ Supervisor vyšetří incident**
# MAGIC
# MAGIC ⬇️
# MAGIC
# MAGIC **2️⃣ Rozhodne, že je potřeba provést akci**
# MAGIC
# MAGIC > „Chci aktualizovat support case CAS-40318.“
# MAGIC
# MAGIC ⬇️
# MAGIC
# MAGIC **3️⃣ Běh se zastaví a požádá uživatele o schválení**
# MAGIC
# MAGIC > ✋ **Approve / Reject**
# MAGIC
# MAGIC ⬇️
# MAGIC
# MAGIC **4️⃣ Teprve po schválení se akce provede**
# MAGIC
# MAGIC Tento princip označujeme jako **human-in-the-loop**.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🛡️ Proč je to důležité?
# MAGIC
# MAGIC Cílem není dát agentovi automaticky přístup ke všemu.
# MAGIC
# MAGIC Cílem je navrhnout **správnou úroveň autonomie pro konkrétní proces**.
# MAGIC
# MAGIC Například:
# MAGIC
# MAGIC | Operace | Možný přístup |
# MAGIC |---|---|
# MAGIC | 🔎 hledání v dokumentaci | autonomně |
# MAGIC | 📊 čtení payroll dat | autonomně |
# MAGIC | 🧮 výpočet SLA kreditu | autonomně |
# MAGIC | 📝 návrh odpovědi zákazníkovi | autonomně |
# MAGIC | 🎫 změna support case | může vyžadovat approval |
# MAGIC | ✉️ odeslání e-mailu zákazníkovi | může vyžadovat approval |
# MAGIC
# MAGIC Nejde tedy jen o otázku:
# MAGIC
# MAGIC > **„Co agent umí?“**
# MAGIC
# MAGIC Stejně důležitá je otázka:
# MAGIC
# MAGIC > **„Co mu dovolíme udělat bez zásahu člověka?“**
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🧠 Agentní systém tak může kombinovat obojí
# MAGIC
# MAGIC **Autonomii tam, kde dává smysl:**
# MAGIC
# MAGIC 🔎 hledání → 🧠 reasoning → 🧮 výpočty → 📝 příprava návrhu
# MAGIC
# MAGIC a současně:
# MAGIC
# MAGIC **lidskou kontrolu tam, kde ji potřebujeme:**
# MAGIC
# MAGIC 🧠 rozhodnutí agenta → ✋ approval → ⚡ provedení citlivé akce
# MAGIC
# MAGIC > 💡 **Human-in-the-loop není náhrada za agenta.**
# MAGIC >
# MAGIC > Je to způsob, jak agentovi umožnit dělat více, aniž bychom se museli vzdát kontroly nad citlivými operacemi.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🧪 Co sledujeme v našem scénáři?
# MAGIC
# MAGIC Pokud Supervisor při řešení úkolu navrhne akci vyžadující schválení:
# MAGIC
# MAGIC 1. Prohlédněte si **jakou akci chce provést**
# MAGIC 2. Zkontrolujte **s jakými parametry ji chce provést**
# MAGIC 3. Rozhodněte se, zda ji chcete **schválit nebo zamítnout**
# MAGIC 4. Sledujte, jak Supervisor po vašem rozhodnutí pokračuje
# MAGIC
# MAGIC Tohle je důležitý posun:
# MAGIC
# MAGIC > **Uživatel už nemusí ručně provádět celý proces. Kontrolu může převzít pouze v těch bodech, kde je jeho rozhodnutí skutečně potřeba.**
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## 🎯 Kam jsme se dostali?
# MAGIC
# MAGIC Začínali jsme jednoduchou otázkou nad payroll tabulkami.
# MAGIC
# MAGIC Teď máme systém, který dokáže:
# MAGIC
# MAGIC **🔎 získávat informace → 🧩 kombinovat různé zdroje → 🧠 plánovat další kroky → 🧮 používat business logiku → ⚡ navrhovat a provádět akce → ✋ zapojit člověka tam, kde je potřeba**
# MAGIC
# MAGIC V další části si celý systém shrneme a podíváme se na architekturu, kterou jsme během workshopu postupně postavili.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🏗️ Krok 12 — Co jsme vlastně postavili?
# MAGIC
# MAGIC Začínali jsme relativně jednoduchým problémem:
# MAGIC
# MAGIC > **47 zaměstnanců Alpine Retail nedostalo výplatu. Proč?**
# MAGIC
# MAGIC Na začátku jsme měli několik různých zdrojů informací a člověk musel sám vědět:
# MAGIC
# MAGIC - kde hledat,
# MAGIC - koho se zeptat,
# MAGIC - jak jednotlivá zjištění propojit,
# MAGIC - co udělat jako další krok.
# MAGIC
# MAGIC Postupně jsme nad jednotlivými zdroji vytvořili nebo připojili **specializované komponenty** a nad ně postavili **Supervisor Agenta**.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### 🧩 Výsledná architektura
# MAGIC
# MAGIC | Potřeba | Specializovaná komponenta |
# MAGIC |---|---|
# MAGIC | 💰 Co se stalo při payrollu? | **Payroll Genie** |
# MAGIC | 🏥 Co se dělo na platformě? | **Platform Health Genie** |
# MAGIC | 📚 Co říká dokumentace? | **Knowledge Assistant** |
# MAGIC | 🔎 Řešili jsme něco podobného? | **AI Search / Vector Search** |
# MAGIC | 🧮 Potřebujeme přesný business výpočet? | **UC Function** |
# MAGIC | 📧 Co jsme komunikovali zákazníkovi? | **Outlook** |
# MAGIC | 🎫 Jaký je stav support případu? | **CaseHub** |
# MAGIC
# MAGIC Nad nimi stojí:
# MAGIC
# MAGIC # 🧠 Supervisor Agent
# MAGIC
# MAGIC Jeho úkolem je jednotlivé specialisty a nástroje **orchestravat**.
# MAGIC
# MAGIC ```text
# MAGIC                               👤 Uživatel
# MAGIC                                   │
# MAGIC                                   ▼
# MAGIC                            🧠 SUPERVISOR
# MAGIC                                   │
# MAGIC           ┌───────────┬───────────┼───────────┬───────────┐
# MAGIC           ▼           ▼           ▼           ▼           ▼
# MAGIC      💰 Payroll   🏥 Platform   📚 Docs    🔎 Search   🧮 Function
# MAGIC         Genie        Genie         KA
# MAGIC           │           │           │           │           │
# MAGIC           └───────────┴───────────┴───────────┴───────────┘
# MAGIC                                   │
# MAGIC                             📧 Outlook
# MAGIC                             🎫 CaseHub
# MAGIC                                   │
# MAGIC                              ✋ Approval
