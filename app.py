"""
Доктор Хаус: Экономическое отделение
Мини-игра на базе DeepSeek API + Streamlit
"""

import streamlit as st
import requests
import json
import re
import random
import base64
from pathlib import Path

# ---------------------------------------------------------------------------
# Настройки и персонажи
# ---------------------------------------------------------------------------

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
ASSETS_DIR = Path(__file__).parent / "assets"

CHARACTERS = {
    "forman": {"name": "Форман", "color": "#D85A30", "bg": "#FAECE7", "avatar": "foreman.jpg"},
    "cameron": {"name": "Кэмерон", "color": "#1D9E75", "bg": "#E1F5EE", "avatar": "cameron.jpg"},
    "chase": {"name": "Чейз", "color": "#378ADD", "bg": "#E6F1FB", "avatar": "chase.jpg"},
    "wilson": {"name": "Уилсон", "color": "#9B6BD1", "bg": "#F0E9F9", "avatar": "wilson.jpg"},
}
TEAM_ORDER = ["forman", "cameron", "chase"]  # участвуют в общем брифинге
ALL_ORDER = ["forman", "cameron", "chase", "wilson"]  # порядок иконок снизу

PERSONA_DESCRIPTIONS = {
    "forman": "Амбициозный интервенционист. Веришь в прямое вмешательство государства. "
              "Немного колючий, любишь быть правым, оберегаешь свою репутацию эксперта.",
    "cameron": "Этик команды. Тебя волнуют люди и социальные последствия, а не только цифры. "
               "Принципиальна, но не наивна — за годы работы стала жёстче.",
    "chase": "Рыночный либерал/ортодокс. Скептичен к вмешательству государства, прагматичен, "
             "иногда цинично-легкомысленный тон, но расчёт у тебя точный.",
    "wilson": "Онколог, лучший друг доктора (игрока) вне отделения экономики. НЕ разбираешься "
              "глубоко в макроэкономике и не даёшь развёрнутых советов по кейсу. Вместо этого "
              "коротко комментируешь самого игрока — его азарт, самоуверенность, упрямство — "
              "тепло, с мягкой иронией и редкими подколами, иногда одной точной философской "
              "мыслью в тему. Твои реплики — 1-3 предложения, не больше.",
}

DIFFICULTY_PROMPTS = {
    "easy": "Уровень СЛОЖНОСТИ: ЛЁГКИЙ. Возьми хорошо известный реальный случай из истории "
            "экономики (например, гиперинфляция в Веймарской Германии, японская дефляционная "
            "ловушка, нефтяной шок 1970-х и т.п.) и представь его почти без маскировки — "
            "страна и цифры близки к реальности, диагноз должен угадываться при базовых знаниях.",
    "medium": "Уровень СЛОЖНОСТИ: СРЕДНИЙ. Возьми реальный исторический экономический случай, "
              "но замаскируй его под вымышленную страну с изменёнными именами и деталями "
              "(как ирландский кризис 2008 под видом «Хайленда»). Игрок должен сам распознать "
              "паттерн, не называя реальную страну напрямую.",
    "hard": "Уровень СЛОЖНОСТИ: СЛОЖНЫЙ. Придумай полностью вымышленную ситуацию, которая "
            "никогда не происходила в реальности, но построена на правдоподобной комбинации "
            "реальных экономических механизмов. Игроку придётся рассуждать с нуля, без опоры "
            "на узнавание исторического паттерна.",
}

SYSTEM_PROMPT_TEMPLATE = """Давай сыграем в игру. Ты — ведущий-нарратор в мире, где экономики —
это пациенты, а я — доктор-диагност вроде Грегори Хауса. Твоя команда — три экономических
консультанта: Форман, Кэмерон, Чейз (описания ниже). Есть также Уилсон — друг игрока, не
участвует в общем брифинге, только в личных разговорах.

{difficulty_instruction}

Описания консультантов:
- Форман: {forman_desc}
- Кэмерон: {cameron_desc}
- Чейз: {chase_desc}

Твои функции как ведущего:
1. Создать кейс: придумай "страну-пациента" со сложной экономической болезнью согласно уровню
   сложности выше. Держи истинный диагноз в секрете до самого конца.
2. Выдать вводные: карточка пациента с цифрами (ВВП, инфляция, безработица, курс) и жалобами.
3. Реагировать на "тесты" и "лечение": игрок запрашивает статистику или предлагает меры
   политики — описывай реакцию экономики, которая может быть неожиданной.
4. Team-реакции: после каждого хода игрока три консультанта (Форман, Кэмерон, Чейз) кратко
   реагируют на его мысль — каждый со своей позиции, 2-4 предложения. ИЗРЕДКА (не каждый раз!)
   пусть один консультант коротко и не зло подколет версию другого, если не согласен — это
   должно происходить редко, чтобы не приедаться.
5. Диагноз: если сообщение игрока похоже на попытку финального диагноза (не просто гипотеза
   по ходу дела, а уверенное заключение) — оцени, насколько оно по СМЫСЛУ совпадает с истинным
   диагнозом (не требуй дословного совпадения терминов). Если совпадение хорошее — открыто
   объяви это в narrator, раскрой истинный диагноз и разбери кейс с точки зрения экономической
   теории, и поставь "case_solved": true. Если диагноз неточный или неполный — укажи, что
   упущено, и предложи продолжить, "case_solved": false. Не начинай эту процедуру, пока игрок
   явно не выдвинул финальную версию.

ФОРМАТ ОТВЕТА — строго валидный JSON, без markdown-разметки, без ```json оберток, только сам
объект:
{{
  "narrator": "текст ведущего",
  "reactions": [
    {{"speaker": "forman", "text": "реплика Формана, 2-4 предложения"}},
    {{"speaker": "cameron", "text": "реплика Кэмерон, 2-4 предложения"}},
    {{"speaker": "chase", "text": "реплика Чейза, 2-4 предложения"}}
  ],
  "case_solved": false
}}

Если это самый первый ход игры (карточка пациента) — reactions может быть пустым списком [].
Отвечай только на русском языке. Начни с первого кейса прямо сейчас."""

PERSONA_SYSTEM_PROMPT = """Ты играешь роль {name} в игре "Доктор Хаус: Экономическое
отделение". {persona_desc}

Идёт приватный разговор один на один с игроком о текущем кейсе. Этот разговор НЕ виден
остальной команде и не влияет на основной сюжет — здесь можно обсуждать подробнее и честнее.

Контекст кейса (последние ходы основной игры):
{case_context}

Правила:
- Отвечай от первого лица, без вводных фраз вроде "как {name}, я думаю" — сразу суть.
- 2-4 предложения на реплику (для Уилсона — 1-3, короче и без лекций).
- Можешь спорить, задавать встречные вопросы, комментировать мнения других членов команды,
  если игрок их упоминает.
- Оставайся в характере. Не веди повествование за ведущего.
- Отвечай на русском языке."""

WILSON_OPENERS = [
    "заходит с двумя стаканами кофе, один молча ставит перед тобой: «Не спрашивай, просто пей.»",
    "подкладывает тебе на стол чью-то чужую карту пациента с запиской «это не смешно, но я всё равно сделал».",
    "уже сидит в кресле, закинув ноги на твой стол: «Ты опять решаешь мировую экономику вместо того, чтобы поесть.»",
    "кидает в тебя мятой бумажкой: «Твоя команда снаружи спорит о тебе. Приятно, да?»",
    "заходит с деланно серьёзным лицом: «Я записал тебя на приём к психотерапевту. Шучу. Или нет.»",
    "молча кладёт руку на плечо и садится напротив, не говоря ни слова — просто ждёт, что ты скажешь.",
]

# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------

@st.cache_data
def load_avatar_b64(filename: str) -> str:
    path = ASSETS_DIR / filename
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode()


def call_deepseek(api_key: str, messages: list[dict], model: str, max_tokens: int = 1300) -> str:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": 0.9, "max_tokens": max_tokens}
    response = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def parse_main_response(raw: str) -> dict:
    cleaned = re.sub(r"^```json\s*|^```\s*|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(cleaned)
        data.setdefault("narrator", raw)
        data.setdefault("reactions", [])
        data.setdefault("case_solved", False)
        return data
    except json.JSONDecodeError:
        return {"narrator": raw, "reactions": [], "case_solved": False}


def build_case_context() -> str:
    snippets = []
    for m in st.session_state.messages[-6:]:
        if m["role"] == "user":
            snippets.append(f"Доктор: {m['content']}")
        elif m["role"] == "assistant":
            data = parse_main_response(m["content"])
            snippets.append(f"[Ход игры]: {data['narrator'][:500]}")
    return "\n".join(snippets)


def build_system_prompt() -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(
        difficulty_instruction=DIFFICULTY_PROMPTS[st.session_state.difficulty],
        forman_desc=PERSONA_DESCRIPTIONS["forman"],
        cameron_desc=PERSONA_DESCRIPTIONS["cameron"],
        chase_desc=PERSONA_DESCRIPTIONS["chase"],
    )


def get_persona_reply(api_key, model, persona_key, solo_thread) -> str:
    persona = CHARACTERS[persona_key]
    system = PERSONA_SYSTEM_PROMPT.format(
        name=persona["name"], persona_desc=PERSONA_DESCRIPTIONS[persona_key],
        case_context=build_case_context(),
    )
    messages = [{"role": "system", "content": system}] + solo_thread
    return call_deepseek(api_key, messages, model, max_tokens=250)


def render_group_reaction(persona_key: str, text: str):
    p = CHARACTERS[persona_key]
    st.markdown(
        f"""<div style="display:flex;gap:10px;margin-bottom:10px;">
        <div style="width:32px;height:32px;border-radius:50%;background:{p['bg']};
        display:flex;align-items:center;justify-content:center;font-size:12px;
        font-weight:600;color:{p['color']};flex-shrink:0;">{p['name'][0]}</div>
        <div style="flex:1;background:{p['bg']}55;border-left:3px solid {p['color']};
        border-radius:0 8px 8px 0;padding:8px 12px;">
        <p style="font-size:12px;font-weight:600;color:{p['color']};margin:0 0 4px;">{p['name']}</p>
        <p style="font-size:14px;margin:0;line-height:1.5;">{text}</p>
        </div></div>""",
        unsafe_allow_html=True,
    )


def render_solo_bubble(persona_key: str, role: str, text: str):
    """Личка: аватар по центру, текст под ним."""
    p = CHARACTERS[persona_key]
    if role == "user":
        st.markdown(
            f"""<div style="text-align:right;margin-bottom:12px;">
            <div style="display:inline-block;background:var(--surface-1,#f0efec);
            border-radius:10px;padding:8px 14px;max-width:80%;font-size:14px;">{text}</div>
            </div>""", unsafe_allow_html=True)
        return
    b64 = load_avatar_b64(p["avatar"])
    img_html = (f'<img src="data:image/jpeg;base64,{b64}" style="width:64px;height:64px;'
                f'border-radius:50%;object-fit:cover;border:2px solid {p["color"]};">'
                if b64 else "")
    st.markdown(
        f"""<div style="text-align:center;margin-bottom:16px;">
        {img_html}
        <p style="font-size:12px;font-weight:600;color:{p['color']};margin:6px 0 4px;">{p['name']}</p>
        <p style="font-size:14px;margin:0 auto;max-width:420px;line-height:1.5;">{text}</p>
        </div>""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Доктор Хаус: Экономическое отделение", page_icon="🩺")
st.title("🩺 Доктор Хаус: Экономическое отделение")

with st.sidebar:
    st.header("Настройки")
    api_key = st.text_input("DeepSeek API ключ", type="password")
    model_choice = st.selectbox("Модель", options=["deepseek-chat", "deepseek-reasoner"])
    difficulty_label = st.selectbox(
        "Сложность кейса",
        options=["easy", "medium", "hard"],
        format_func=lambda x: {"easy": "Лёгкий — известный случай",
                                "medium": "Средний — замаскированный реальный",
                                "hard": "Сложный — полностью вымышленный"}[x],
    )
    st.divider()
    if st.button("🔄 Новый кейс"):
        st.session_state.messages = []
        st.session_state.solo_threads = {}
        st.session_state.open_panel = None
        st.session_state.difficulty = difficulty_label
        st.rerun()
    st.divider()
    st.markdown("**Ключ:** platform.deepseek.com → API Keys → Create new key")

for key, default in [("messages", []), ("solo_threads", {}), ("open_panel", None),
                      ("difficulty", difficulty_label)]:
    if key not in st.session_state:
        st.session_state[key] = default

# ---------------------------------------------------------------------------
# История основного брифинга
# ---------------------------------------------------------------------------

for msg in st.session_state.messages:
    if msg["role"] == "system":
        continue
    if msg["role"] == "user":
        with st.chat_message("user"):
            st.markdown(msg["content"])
    else:
        with st.chat_message("assistant"):
            data = parse_main_response(msg["content"])
            st.markdown(data["narrator"])
            for r in data["reactions"]:
                if r["speaker"] in CHARACTERS:
                    render_group_reaction(r["speaker"], r["text"])
            if data.get("case_solved"):
                st.success("🏆 Кейс раскрыт!")

# ---------------------------------------------------------------------------
# Старт игры
# ---------------------------------------------------------------------------

if not st.session_state.messages:
    if not api_key:
        st.info("Введи API-ключ DeepSeek в панели слева, чтобы начать игру.")
    else:
        with st.spinner("Готовим первого пациента..."):
            try:
                st.session_state.messages.append({"role": "system", "content": build_system_prompt()})
                reply = call_deepseek(api_key, st.session_state.messages, model_choice)
                st.session_state.messages.append({"role": "assistant", "content": reply})
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка: {e}")

# ---------------------------------------------------------------------------
# Иконки снизу: общее обсуждение + личка с каждым персонажем
# ---------------------------------------------------------------------------

if api_key and st.session_state.messages:
    st.divider()
    cols = st.columns(len(ALL_ORDER) + 1)
    if cols[0].button("🗣️ Общее"):
        st.session_state.open_panel = "general"
    for i, key in enumerate(ALL_ORDER, start=1):
        p = CHARACTERS[key]
        if cols[i].button(p["name"]):
            st.session_state.open_panel = key
            if key not in st.session_state.solo_threads:
                st.session_state.solo_threads[key] = []
                if key == "wilson":
                    opener = random.choice(WILSON_OPENERS)
                    st.session_state.solo_threads[key].append(
                        {"role": "assistant", "content": f"*{opener}*"}
                    )

    panel = st.session_state.open_panel

    # --- Панель "Общее обсуждение" ---
    if panel == "general":
        st.caption("⚠️ Сообщение здесь сразу запускает новый общий брифинг команды.")
        general_input = st.chat_input("Твоя мысль для всей команды...")
        if general_input:
            st.session_state.messages.append({"role": "user", "content": general_input})
            with st.spinner("Экономика реагирует..."):
                try:
                    reply = call_deepseek(api_key, st.session_state.messages, model_choice)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                    st.session_state.open_panel = None
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка: {e}")

    # --- Панель личного разговора ---
    elif panel in CHARACTERS:
        p = CHARACTERS[panel]
        st.markdown(f"#### 💬 Личный разговор с {p['name']}")
        for m in st.session_state.solo_threads[panel]:
            render_solo_bubble(panel, m["role"], m["content"])
        solo_input = st.chat_input(f"Написать {p['name']}...")
        if solo_input:
            st.session_state.solo_threads[panel].append({"role": "user", "content": solo_input})
            with st.spinner(f"{p['name']} отвечает..."):
                try:
                    reply = get_persona_reply(api_key, model_choice, panel,
                                               st.session_state.solo_threads[panel])
                    st.session_state.solo_threads[panel].append({"role": "assistant", "content": reply})
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка: {e}")

    # --- Обычный ввод в основной брифинг (без выбранной панели) ---
    else:
        user_input = st.chat_input("Твой ход (вопрос, гипотеза, назначение анализа...)")
        if user_input:
            st.session_state.messages.append({"role": "user", "content": user_input})
            with st.spinner("Экономика реагирует..."):
                try:
                    reply = call_deepseek(api_key, st.session_state.messages, model_choice)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка: {e}")
