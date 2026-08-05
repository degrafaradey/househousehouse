"""
Доктор Хаус: Экономическое отделение
Мини-игра на базе DeepSeek API + Streamlit

Ключ читается из st.secrets — см. .streamlit/secrets.toml.example
"""

import streamlit as st
import requests
import json
import re
import random
import base64
from pathlib import Path

DEEPSEEK_API_KEY = st.secrets.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
ASSETS_DIR = Path(__file__).parent / "assets"

CHARACTERS = {
    "forman": {"name": "Форман", "color": "#D85A30", "bg": "#FAECE7", "avatar": "foreman.jpg"},
    "cameron": {"name": "Кэмерон", "color": "#1D9E75", "bg": "#E1F5EE", "avatar": "cameron.jpg"},
    "chase": {"name": "Чейз", "color": "#378ADD", "bg": "#E6F1FB", "avatar": "chase.jpg"},
    "wilson": {"name": "Уилсон", "color": "#9B6BD1", "bg": "#F0E9F9", "avatar": "wilson.jpg"},
}
TEAM_ORDER = ["forman", "cameron", "chase"]
ALL_ORDER = ["forman", "cameron", "chase", "wilson"]

PERSONA_DESCRIPTIONS = {
    "forman": "Амбициозный интервенционист. Веришь в прямое вмешательство государства. "
              "Немного колючий, любишь быть правым, оберегаешь свою репутацию эксперта.",
    "cameron": "Этик команды. Тебя волнуют люди и социальные последствия, а не только цифры. "
               "Принципиальна, но не наивна.",
    "chase": "Рыночный либерал/ортодокс. Скептичен к вмешательству государства, прагматичен, "
             "иногда цинично-легкомысленный тон, но расчёт у тебя точный.",
    "wilson": "Онколог, лучший друг игрока вне отделения экономики. Ты НЕ знаешь деталей "
              "текущего экономического кейса заранее — только то, что игрок сам расскажет тебе "
              "в этом разговоре. Ты не эксперт по макроэкономике. Твоя ценность — свежий "
              "взгляд со стороны, дружеская ирония, редкие подколы и иногда одна точная "
              "философская мысль, которая помогает взглянуть на ситуацию иначе. Не притворяйся, "
              "что знаешь то, чего игрок тебе не говорил. 1-3 предложения на реплику.",
}

MODE_PROMPTS = {
    "real_open": "РЕЖИМ: реальный кейс БЕЗ маскировки. Возьми настоящий известный экономический "
                 "случай — реальная страна, реальные названия и цифры, без вымысла.",
    "real_masked": "РЕЖИМ: реальный кейс С маскировкой. Возьми РЕАЛЬНЫЙ исторический случай "
                   "целиком — цифры, события, механизм и хронология строго соответствуют "
                   "реальности. Замени ТОЛЬКО название страны и имена собственные на "
                   "вымышленные. ЗАПРЕЩЕНО добавлять любые факты сверх реальных. Если игрок "
                   "прямо угадает реальный первоисточник — честно подтверди, не отнекивайся.",
    "fictional": "РЕЖИМ: полностью вымышленный кейс. Придумай вымышленную страну и вымышленную "
                 "ситуацию с нуля. НЕ используй реальные существующие или существовавшие страны "
                 "(США, Россия, Ирландия и т.п.) даже с изменёнными деталями — только "
                 "полностью придуманный мир, чтобы игрок не мог узнать реальный прототип.",
}

COMPLEXITY_PROMPTS = {
    "easy": "СЛОЖНОСТЬ: лёгкая. Минимум ложных версий — почти все зацепки ведут к правильному "
            "диагнозу. Диагноз — ОДНА ясная причина, без наложенных слоёв. При проверке "
            "diagnosis_check принимай даже общую, но верную по сути формулировку как 'solved'.",
    "medium": "СЛОЖНОСТЬ: средняя. Добавь 1-2 правдоподобные, но неверные версии, которые "
              "поначалу могут выглядеть убедительно. Диагноз — основная причина плюс один "
              "усугubляющий фактор. Для 'solved' требуй, чтобы игрок назвал оба элемента, иначе "
              "'correct_with_gaps'.",
    "hard": "СЛОЖНОСТЬ: высокая. Введи 2-3 правдоподобные ложные версии и хотя бы одного "
            "агента, чьи слова прямо вводят в заблуждение (необязательно злонамеренно). Диагноз "
            "состоит из 2-3 переплетённых причин. Для 'solved' игрок должен связать их все.",
    "impossible": "СЛОЖНОСТЬ: невозможная. Введи много ложных версий и минимум двух агентов, "
                  "чьи объяснения противоречат реальным данным (ложь или искреннее "
                  "заблуждение). Диагноз — сложная композиция из 3+ взаимосвязанных причин и "
                  "механизмов. 'solved' — только при очень точном и полном объяснении, "
                  "покрывающем всю цепочку; при частично верном ответе используй "
                  "'correct_with_gaps' и указывай на самые тонкие упущенные нюансы.",
}

SYSTEM_PROMPT_TEMPLATE = """Давай сыграем в игру. Ты — ведущий-нарратор в мире, где экономики —
это пациенты, а я — доктор-диагност вроде Грегори Хауса. Твоя команда — три экономических
консультанта: Форман, Кэмерон, Чейз. Есть также Уилсон — друг игрока вне игры, не участвует в
общем брифинге, только в личных разговорах, и ничего не знает о кейсе заранее.

{mode_instruction}

{complexity_instruction}

Описания консультантов:
- Форман: {forman_desc}
- Кэмерон: {cameron_desc}
- Чейз: {chase_desc}

ВАЖНО про поле "narrator": пиши в нём ТОЛЬКО фактическую игровую информацию — карточку
пациента, результаты "анализов", реакцию экономики. НЕ добавляй туда собственные объяснения
или оценки от своего лица как рассказчика — вся аналитика идёт ИСКЛЮЧИТЕЛЬНО через реплики
Формана, Кэмерон и Чейза в поле "reactions".

КРИТИЧЕСКИ ВАЖНО про поле "reactions": ты ОБЯЗАН вернуть РОВНО 3 объекта — для forman, cameron
и chase, в каждом ходу без исключений (кроме случая, когда это самый первый ход и команда ещё
не видела кейс — тогда допустим пустой список). Никогда не пропускай персонажа и не смешивай
реплики нескольких персонажей в одном объекте.

Твои функции:
1. Создать кейс согласно режиму и сложности выше. Держи истинный диагноз в секрете.
2. При самом первом ходе — карточка пациента (жалобы, объективные цифры) И список из 5-8
   конкретных объективных СИМПТОМОВ в поле "symptoms" (короткие пункты, например "ВВП: −6% за
   два года").
3. Реагировать на "тесты"/"лечение" игрока — через narrator.
4. Team-реакции: 5-8 предложений на реплику каждого из трёх. Изредка (не каждый раз) кто-то
   может коротко и не зло подколоть версию другого при несогласии.
5. Диагноз и "diagnosis_check": оценивай каждый ход на предмет финальной попытки диагноза.
   - Полностью верно → status="solved", "case_solved": true, раскрой диагноз в narrator.
   - Верно по сути, но не хватает деталей → status="correct_with_gaps". В поле
     "missing_details" НЕ пиши сухой список упущенного. Вместо этого напиши 2-4 предложения от
     первого лица случайного ЖИТЕЛЯ страны — он описывает свой личный опыт ситуации бытовым,
     эмоциональным языком, может путать причину со следствием, может повторять то, что ему
     сказали чиновники или банк (необязательно правду). Через этот рассказ внимательный игрок
     должен САМ понять, что именно упущено — не давай прямых подсказок в лоб.
   - Промежуточная мысль/вопрос → status="in_progress".
6. "symptom_status": при диагнозе — список true/false той же длины/порядка, что symptoms,
   накопительно. Если диагноза ещё не было — пустой список или всё false.

ФОРМАТ ОТВЕТА — строго валидный JSON, без markdown и ```json оберток:
{{
  "narrator": "фактический текст",
  "reactions": [
    {{"speaker": "forman", "text": "..."}},
    {{"speaker": "cameron", "text": "..."}},
    {{"speaker": "chase", "text": "..."}}
  ],
  "symptoms": [],
  "diagnosis_check": {{"status": "in_progress", "missing_details": ""}},
  "symptom_status": [],
  "case_solved": false
}}
"symptoms" заполняй ТОЛЬКО в первом ходе. Отвечай только на русском. Начни первый кейс сейчас."""

FINALIZE_MESSAGE = ("Игрок решил зафиксировать текущий диагноз как финальный, несмотря на "
                     "упомянутые упущенные детали. Заверши кейс: подтверди верные тезисы, "
                     "раскрой полный истинный диагноз, честно перечисли упущенные детали и "
                     "почему они важны, оцени ход рассуждений игрока. status='solved', "
                     "case_solved=true.")

PERSONA_SYSTEM_PROMPT = """Ты играешь роль {name} в игре "Доктор Хаус: Экономическое
отделение". {persona_desc}

Идёт приватный разговор один на один с игроком. Не виден команде, не влияет на сюжет.

{context_block}

Правила:
- От первого лица, без вводных фраз вроде "как {name}, я думаю" — сразу суть.
- 2-4 предложения (для Уилсона 1-3).
- Оставайся в характере, не веди повествование за ведущего.
- Отвечай на русском."""

PERSONA_OPENING_PROMPT = """Игрок только что открыл переписку с тобой снова. С момента вашего
последнего разговора произошли новые события в основном кейсе (см. контекст выше). Дай
короткую свежую реакцию от своего лица — не повтор брифинга, а личный неформальный комментарий.
2-4 предложения."""

WILSON_OPENERS = [
    "заходит с двумя стаканами кофе, один молча ставит перед тобой: «Не спрашивай, просто пей.»",
    "подкладывает тебе на стол чью-то чужую карту пациента с запиской «это не смешно, но я всё равно сделал».",
    "уже сидит в кресле, закинув ноги на твой стол: «Ты опять решаешь мировую экономику вместо того, чтобы поесть.»",
    "кидает в тебя мятой бумажкой: «Твоя команда снаружи спорит о тебе. Приятно, да?»",
    "заходит с деланно серьёзным лицом: «Я записал тебя на приём к психотерапевту. Шучу. Или нет.»",
    "молча кладёт руку на плечо и садится напротив, не говоря ни слова — просто ждёт, что ты скажешь.",
]

MODE_LABELS = {"real_open": "Реальный, без маскировки", "real_masked": "Реальный, замаскированный",
               "fictional": "Полностью вымышленный"}
COMPLEXITY_LABELS = {"easy": "Лёгкая", "medium": "Средняя", "hard": "Сложная", "impossible": "Невозможная"}

# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------

@st.cache_data
def load_avatar_b64(filename: str) -> str:
    path = ASSETS_DIR / filename
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode()


def call_deepseek(messages: list[dict], model: str, max_tokens: int = 2500) -> str:
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": 0.9, "max_tokens": max_tokens}
    response = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=90)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def parse_main_response(raw: str) -> dict:
    cleaned = re.sub(r"^```json\s*|^```\s*|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        data = {}
    data.setdefault("narrator", raw)
    data.setdefault("reactions", [])
    data.setdefault("symptoms", [])
    data.setdefault("diagnosis_check", {"status": "in_progress", "missing_details": ""})
    data.setdefault("symptom_status", [])
    data.setdefault("case_solved", False)
    return data


def build_case_context() -> str:
    snippets = []
    for m in st.session_state.messages[-6:]:
        if m["role"] == "user":
            snippets.append(f"Доктор: {m['content']}")
        elif m["role"] == "assistant":
            data = parse_main_response(m["content"])
            snippets.append(f"[Ход игры]: {data['narrator'][:500]}")
    return "\n".join(snippets)


def build_other_threads_context(exclude_key: str) -> str:
    parts = []
    for key in ALL_ORDER:
        if key == exclude_key:
            continue
        thread = st.session_state.solo_threads.get(key, [])
        if not thread:
            continue
        tail = thread[-2:]
        name = CHARACTERS[key]["name"]
        lines = [f'{"Доктор" if m["role"]=="user" else name}: {m["content"][:200]}' for m in tail]
        parts.append(f"Обрывок переписки с {name}:\n" + "\n".join(lines))
    if not parts:
        return ""
    return "Другие приватные разговоры игрока (необязательно упоминать):\n" + "\n\n".join(parts)


def build_system_prompt() -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(
        mode_instruction=MODE_PROMPTS[st.session_state.mode],
        complexity_instruction=COMPLEXITY_PROMPTS[st.session_state.complexity],
        forman_desc=PERSONA_DESCRIPTIONS["forman"],
        cameron_desc=PERSONA_DESCRIPTIONS["cameron"],
        chase_desc=PERSONA_DESCRIPTIONS["chase"],
    )


def build_persona_context_block(persona_key: str) -> str:
    if persona_key == "wilson":
        other = build_other_threads_context(persona_key)
        note = ("Ты НЕ знаешь деталей текущего кейса — только то, что игрок сам расскажет "
                "тебе в этом диалоге.")
        return f"{note}\n\n{other}" if other else note
    return (f"Контекст основного кейса (последние ходы брифинга):\n{build_case_context()}\n\n"
            f"{build_other_threads_context(persona_key)}")


def get_persona_reply(persona_key, model, solo_thread) -> str:
    persona = CHARACTERS[persona_key]
    system = PERSONA_SYSTEM_PROMPT.format(
        name=persona["name"], persona_desc=PERSONA_DESCRIPTIONS[persona_key],
        context_block=build_persona_context_block(persona_key),
    )
    messages = [{"role": "system", "content": system}] + solo_thread
    return call_deepseek(messages, model, max_tokens=300)


def get_persona_opening(persona_key, model) -> str:
    persona = CHARACTERS[persona_key]
    system = PERSONA_SYSTEM_PROMPT.format(
        name=persona["name"], persona_desc=PERSONA_DESCRIPTIONS[persona_key],
        context_block=build_persona_context_block(persona_key),
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": PERSONA_OPENING_PROMPT},
    ]
    return call_deepseek(messages, model, max_tokens=200)


def render_group_reaction(persona_key: str, text: str):
    p = CHARACTERS[persona_key]
    html = (
        f'<div style="display:flex;gap:10px;margin-bottom:10px;">'
        f'<div style="width:32px;height:32px;border-radius:50%;background:{p["bg"]};'
        f'display:flex;align-items:center;justify-content:center;font-size:12px;'
        f'font-weight:600;color:{p["color"]};flex-shrink:0;">{p["name"][0]}</div>'
        f'<div style="flex:1;background:{p["bg"]}55;border-left:3px solid {p["color"]};'
        f'border-radius:0 8px 8px 0;padding:8px 12px;">'
        f'<p style="font-size:12px;font-weight:600;color:{p["color"]};margin:0 0 4px;">{p["name"]}</p>'
        f'<p style="font-size:14px;margin:0;line-height:1.5;">{text}</p>'
        f'</div></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_solo_bubble(persona_key: str, role: str, text: str):
    p = CHARACTERS[persona_key]
    if role == "user":
        html = (
            f'<div style="text-align:right;margin-bottom:12px;">'
            f'<div style="display:inline-block;background:rgba(150,150,150,0.15);'
            f'border-radius:10px;padding:8px 14px;max-width:80%;font-size:14px;">{text}</div>'
            f'</div>'
        )
        st.markdown(html, unsafe_allow_html=True)
        return
    b64 = load_avatar_b64(p["avatar"])
    img_html = (
        f'<img src="data:image/jpeg;base64,{b64}" style="width:64px;height:64px;'
        f'border-radius:50%;object-fit:cover;border:2px solid {p["color"]};">'
        if b64 else ""
    )
    html = (
        f'<div style="text-align:center;margin-bottom:16px;">'
        f'{img_html}'
        f'<p style="font-size:12px;font-weight:600;color:{p["color"]};margin:6px 0 4px;">{p["name"]}</p>'
        f'<p style="font-size:14px;margin:0 auto;max-width:420px;line-height:1.5;">{text}</p>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def apply_main_response(reply: str):
    st.session_state.messages.append({"role": "assistant", "content": reply})
    data = parse_main_response(reply)
    if data["symptoms"]:
        st.session_state.case_symptoms = data["symptoms"]
        st.session_state.symptom_status = [False] * len(data["symptoms"])
    if data.get("symptom_status") and len(data["symptom_status"]) == len(st.session_state.case_symptoms):
        st.session_state.symptom_status = data["symptom_status"]


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Доктор Хаус: Экономическое отделение", page_icon="🩺")
st.title("🩺 Доктор Хаус: Экономическое отделение")

with st.sidebar:
    st.header("Настройки")
    model_choice = st.selectbox("Модель", options=["deepseek-chat", "deepseek-reasoner"])
    st.divider()
    if st.button("🔄 Новый кейс"):
        for k in ["messages", "solo_threads", "open_panel", "case_symptoms", "symptom_status",
                  "solo_context_len", "solo_collapsed", "dismissed_warnings", "mode", "complexity"]:
            st.session_state.pop(k, None)
        st.rerun()

defaults = {
    "messages": [], "solo_threads": {}, "open_panel": None, "case_symptoms": [],
    "symptom_status": [], "solo_context_len": {}, "solo_collapsed": {},
    "dismissed_warnings": set(), "mode": None, "complexity": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ---------------------------------------------------------------------------
# Экран старта: выбор режима + сложности
# ---------------------------------------------------------------------------

if not st.session_state.messages:
    st.write("Диагностируй больную экономику. Опрашивай команду, назначай 'анализы', ищи диагноз.")
    if not DEEPSEEK_API_KEY:
        st.error("Ключ DeepSeek не найден в secrets. См. .streamlit/secrets.toml.example")
        st.stop()

    st.session_state.mode = st.radio(
        "Режим", options=list(MODE_PROMPTS), format_func=lambda x: MODE_LABELS[x], horizontal=True,
    )
    st.session_state.complexity = st.radio(
        "Сложность", options=list(COMPLEXITY_PROMPTS), format_func=lambda x: COMPLEXITY_LABELS[x],
        horizontal=True,
    )

    if st.button("▶️ Начать играть", type="primary"):
        with st.spinner("Готовим первого пациента..."):
            try:
                st.session_state.messages.append({"role": "system", "content": build_system_prompt()})
                reply = call_deepseek(st.session_state.messages, model_choice)
                apply_main_response(reply)
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка: {e}")
    st.stop()

# ---------------------------------------------------------------------------
# Окно симптомов
# ---------------------------------------------------------------------------

if st.session_state.case_symptoms:
    solved_count = sum(st.session_state.symptom_status)
    total = len(st.session_state.case_symptoms)
    with st.expander(f"📋 Симптомы кейса ({solved_count}/{total} объяснено)"):
        for i, s in enumerate(st.session_state.case_symptoms):
            mark = "✅" if i < len(st.session_state.symptom_status) and st.session_state.symptom_status[i] else "⬜"
            st.markdown(f"{mark} {s}")

# ---------------------------------------------------------------------------
# История основного брифинга
# ---------------------------------------------------------------------------

for idx, msg in enumerate(st.session_state.messages):
    if msg["role"] == "system":
        continue
    if msg["role"] == "user":
        if msg["content"] == FINALIZE_MESSAGE:
            st.caption("— игрок зафиксировал финальный диагноз —")
            continue
        with st.chat_message("user"):
            st.markdown(msg["content"])
    else:
        with st.chat_message("assistant"):
            data = parse_main_response(msg["content"])
            st.markdown(data["narrator"])
            for r in data["reactions"]:
                if r["speaker"] in CHARACTERS:
                    render_group_reaction(r["speaker"], r["text"])
            if len(data["reactions"]) < 3 and len(st.session_state.case_symptoms) > 0:
                st.caption("⚠️ Кто-то из команды промолчал в этот раз (сбой генерации) — не критично, продолжай.")

            check = data.get("diagnosis_check", {})
            is_last = (idx == len(st.session_state.messages) - 1)

            if data.get("case_solved"):
                st.success("🏆 Кейс раскрыт!")
            elif check.get("status") == "correct_with_gaps" and is_last and idx not in st.session_state.dismissed_warnings:
                st.markdown(
                    f'<div style="background:rgba(240,180,40,0.12);border-left:3px solid #E0A82E;'
                    f'border-radius:0 8px 8px 0;padding:10px 14px;margin:10px 0;">'
                    f'<p style="font-size:12px;font-weight:600;color:#C68A1E;margin:0 0 6px;">'
                    f'✅ Диагноз в целом верный. Голос с улицы:</p>'
                    f'<p style="font-size:14px;font-style:italic;margin:0;line-height:1.5;">'
                    f'«{check.get("missing_details", "")}»</p></div>',
                    unsafe_allow_html=True,
                )
                c1, c2 = st.columns(2)
                if c1.button("✅ Завершить", key=f"finalize_{idx}"):
                    st.session_state.messages.append({"role": "user", "content": FINALIZE_MESSAGE})
                    with st.spinner("Подводим итоги..."):
                        try:
                            reply = call_deepseek(st.session_state.messages, model_choice)
                            apply_main_response(reply)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Ошибка: {e}")
                if c2.button("🔍 Копать дальше", key=f"continue_{idx}"):
                    st.session_state.dismissed_warnings.add(idx)
                    st.rerun()

# ---------------------------------------------------------------------------
# Иконки снизу
# ---------------------------------------------------------------------------

st.divider()
cols = st.columns(len(ALL_ORDER) + 1)
if cols[0].button("🗣️ Общее"):
    st.session_state.open_panel = "general"
for i, key in enumerate(ALL_ORDER, start=1):
    if cols[i].button(CHARACTERS[key]["name"]):
        st.session_state.open_panel = key
        current_len = len(st.session_state.messages)
        thread_empty = not st.session_state.solo_threads.get(key)
        if thread_empty:
            st.session_state.solo_threads[key] = []
            if key == "wilson":
                opener = random.choice(WILSON_OPENERS)
                st.session_state.solo_threads[key].append({"role": "assistant", "content": f"*{opener}*"})
            else:
                with st.spinner(f"{CHARACTERS[key]['name']} думает..."):
                    try:
                        opening = get_persona_opening(key, model_choice)
                        st.session_state.solo_threads[key].append({"role": "assistant", "content": opening})
                        st.session_state.solo_context_len[key] = current_len
                    except Exception as e:
                        st.error(f"Ошибка: {e}")
        elif key != "wilson" and st.session_state.solo_context_len.get(key) != current_len:
            with st.spinner(f"{CHARACTERS[key]['name']} думает..."):
                try:
                    opening = get_persona_opening(key, model_choice)
                    st.session_state.solo_threads[key].append({"role": "assistant", "content": opening})
                    st.session_state.solo_context_len[key] = current_len
                except Exception as e:
                    st.error(f"Ошибка: {e}")

panel = st.session_state.open_panel

if panel == "general":
    st.caption("⚠️ Сообщение здесь сразу запускает новый общий брифинг команды.")
    general_input = st.chat_input("Твоя мысль для всей команды...")
    if general_input:
        st.session_state.messages.append({"role": "user", "content": general_input})
        with st.spinner("Экономика реагирует..."):
            try:
                reply = call_deepseek(st.session_state.messages, model_choice)
                apply_main_response(reply)
                st.session_state.open_panel = None
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка: {e}")

elif panel in CHARACTERS:
    p = CHARACTERS[panel]
    st.markdown(f"#### 💬 Личный разговор с {p['name']}")

    collapsed = st.session_state.solo_collapsed.get(panel, False)
    thread = st.session_state.solo_threads.get(panel, [])

    if collapsed:
        st.caption(f"История скрыта ({len(thread)} сообщ.)")
    else:
        for m in thread:
            render_solo_bubble(panel, m["role"], m["content"])

    if st.button("🔽 Свернуть" if not collapsed else "🔼 Показать историю", key=f"toggle_{panel}"):
        st.session_state.solo_collapsed[panel] = not collapsed
        st.rerun()

    solo_input = st.chat_input(f"Написать {p['name']}...")
    if solo_input:
        st.session_state.solo_threads[panel].append({"role": "user", "content": solo_input})
        with st.spinner(f"{p['name']} отвечает..."):
            try:
                reply = get_persona_reply(panel, model_choice, st.session_state.solo_threads[panel])
                st.session_state.solo_threads[panel].append({"role": "assistant", "content": reply})
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка: {e}")

else:
    user_input = st.chat_input("Твой ход (вопрос, гипотеза, назначение анализа...)")
    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.spinner("Экономика реагирует..."):
            try:
                reply = call_deepseek(st.session_state.messages, model_choice)
                apply_main_response(reply)
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка: {e}")
