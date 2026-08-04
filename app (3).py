"""
Доктор Хаус: Экономическое отделение
Мини-игра на базе DeepSeek API + Streamlit

Ключ DeepSeek читается из st.secrets — он НЕ хранится в этом файле и не попадёт в
публичный репозиторий. Настройка:

  Локально:
    1. Создай файл .streamlit/secrets.toml рядом с app.py
    2. Впиши туда: DEEPSEEK_API_KEY = "sk-..."
    3. Добавь .streamlit/secrets.toml в .gitignore, чтобы git его не закоммитил

  На Streamlit Cloud:
    Настройки приложения → Settings → Secrets → вставь туда ту же строку
    DEEPSEEK_API_KEY = "sk-..." через веб-интерфейс.
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
    "wilson": "Онколог, лучший друг игрока вне отделения экономики. НЕ разбираешься глубоко "
              "в макроэкономике и не даёшь развёрнутых советов по кейсу. Коротко комментируешь "
              "самого игрока — его азарт, самоуверенность, упрямство — тепло, с мягкой иронией "
              "и редкими подколами, иногда одной точной философской мыслью. 1-3 предложения.",
}

DIFFICULTY_PROMPTS = {
    "easy": "Уровень СЛОЖНОСТИ: ЛЁГКИЙ. Возьми хорошо известный реальный экономический случай "
            "и представь его БЕЗ какой-либо маскировки — реальная страна, реальные названия и "
            "цифры. Диагноз (что произошло) должен быть довольно очевиден. Основная задача "
            "игрока на этом уровне — не угадать диагноз, а предложить работающее РЕШЕНИЕ "
            "проблемы, обсуждая его с командой.",
    "medium": "Уровень СЛОЖНОСТИ: СРЕДНИЙ. Возьми РЕАЛЬНЫЙ исторический экономический случай "
              "целиком — все цифры, события, механизмы и хронология должны СТРОГО "
              "соответствовать реальной истории. Замаскируй ТОЛЬКО название страны и имена "
              "собственные (страна, валюта, персоналии) на вымышленные. ЗАПРЕЩЕНО добавлять, "
              "изменять или выдумывать любые фактические детали, события или цифры сверх того, "
              "что было в реальности — это не творческая адаптация, а точная маскировка "
              "реального случая под псевдонимом. Если тебя спросят прямо, какая это реальная "
              "история — не изворачивайся, а признай честно, что игрок прав, если он угадал "
              "правильно.",
    "hard": "Уровень СЛОЖНОСТИ: СЛОЖНЫЙ. Либо придумай полностью вымышленную ситуацию, либо "
            "возьми настоящую страну (существующую или существовавшую) и помести её в "
            "вымышленные обстоятельства/события, которых не было в реальности. Игрок не "
            "должен иметь возможность разгадать это узнаванием реальной истории — рассуждать "
            "придётся с нуля.",
}

SYSTEM_PROMPT_TEMPLATE = """Давай сыграем в игру. Ты — ведущий-нарратор в мире, где экономики —
это пациенты, а я — доктор-диагност вроде Грегори Хауса. Твоя команда — три экономических
консультанта: Форман, Кэмерон, Чейз. Есть также Уилсон — друг игрока, не участвует в общем
брифинге, только в личных разговорах.

{difficulty_instruction}

Описания консультантов:
- Форман: {forman_desc}
- Кэмерон: {cameron_desc}
- Чейз: {chase_desc}

ВАЖНО про поле "narrator": пиши в нём ТОЛЬКО фактическую игровую информацию — карточку
пациента, результаты запрошенных "анализов", реакцию экономики на действия игрока. НЕ добавляй
туда собственные объяснения, интерпретации или оценочные суждения от своего лица как
рассказчика — вся аналитика и мнения должны идти ИСКЛЮЧИТЕЛЬНО через реплики Формана, Кэмерон
и Чейза в поле "reactions".

Твои функции:
1. Создать кейс согласно уровню сложности выше. Держи истинный диагноз в секрете.
2. При самом первом ходе — дай карточку пациента (жалобы, объективные цифры) И список из
   5-8 конкретных объективных СИМПТОМОВ кейса в поле "symptoms" (короткие пункты, как в
   медицинской карте, например "ВВП: −6% за два года", "Госдолг вырос с 50% до 130% ВВП").
3. Реагировать на "тесты" и "лечение" игрока — через narrator.
4. Team-реакции: после каждого хода три консультанта реагируют на мысль игрока, каждый со
   своей позиции, ТЕПЕРЬ 5-8 предложений на реплику (это больше, чем раньше, потому что
   narrator больше не даёт своих объяснений — вся глубина теперь в репликах команды). Изредка
   (не каждый раз) кто-то может коротко и не зло подколоть версию другого при несогласии.
5. Диагноз и поле "diagnosis_check": оценивай КАЖДЫЙ ход игрока на предмет того, не звучит ли
   он как попытка финального диагноза. Если это явно финальная версия:
   - Если она верна и покрывает суть механизма ПОЛНОСТЬЮ — status="solved", "case_solved": true,
     раскрой в narrator истинный диагноз и разбери кейс.
   - Если она верна по СУТИ (правильный механизм, правильная причина), но упущены важные
     детали или нюансы — status="correct_with_gaps", НЕ раскрывай сразу диагноз в narrator,
     а в поле "missing_details" коротко перечисли, что именно упущено.
   - Если это не похоже на финальную попытку, а промежуточная мысль/вопрос — status="in_progress".
6. Поле "symptom_status": если игрок только что дал диагноз (correct_with_gaps или solved),
   верни список true/false той же длины и в том же порядке, что исходный список symptoms —
   какие из симптомов игрок корректно объяснил своим диагнозом на данный момент (накопительно,
   учитывай и то, что было объяснено раньше в игре). Если диагноз ещё не звучал — просто верни
   список из всех false или не включай это поле вовсе.

ФОРМАТ ОТВЕТА — строго валидный JSON, без markdown-разметки и ```json оберток:
{{
  "narrator": "фактический текст: карточка пациента / результаты / реакция экономики",
  "reactions": [
    {{"speaker": "forman", "text": "реплика Формана, 5-8 предложений"}},
    {{"speaker": "cameron", "text": "реплика Кэмерон, 5-8 предложений"}},
    {{"speaker": "chase", "text": "реплика Чейза, 5-8 предложений"}}
  ],
  "symptoms": ["симптом 1", "симптом 2", "..."],
  "diagnosis_check": {{"status": "in_progress", "missing_details": ""}},
  "symptom_status": [],
  "case_solved": false
}}
Поле "symptoms" заполняй ТОЛЬКО в самом первом ходе игры, в остальных — пустой список [].
Отвечай только на русском языке. Начни с первого кейса прямо сейчас."""

FINALIZE_MESSAGE = ("Игрок решил зафиксировать текущий диагноз как финальный, несмотря на "
                     "упомянутые упущенные детали. Заверши кейс: подтверди верные тезисы "
                     "игрока, раскрой полный истинный диагноз, честно перечисли, какие "
                     "детали/нюансы были упущены и почему они важны, оцени ход рассуждений "
                     "игрока в целом (что было сильным, что слабым). Установи status='solved' "
                     "и case_solved=true.")

PERSONA_SYSTEM_PROMPT = """Ты играешь роль {name} в игре "Доктор Хаус: Экономическое
отделение". {persona_desc}

Идёт приватный разговор один на один с игроком о текущем кейсе. Этот разговор НЕ виден
остальной команде и не влияет на основной сюжет.

Контекст основного кейса (последние ходы общего брифинга):
{case_context}

{other_threads_context}

Правила:
- Отвечай от первого лица, без вводных фраз вроде "как {name}, я думаю" — сразу суть.
- 2-4 предложения на реплику (для Уилсона — 1-3, короче и без лекций).
- Можешь ссылаться на то, что игрок обсуждал с другими членами команды в их личках, если это
  естественно в разговоре — но не обязательно каждый раз.
- Оставайся в характере, не веди повествование за ведущего.
- Отвечай на русском языке."""

PERSONA_OPENING_PROMPT = """Игрок только что открыл переписку с тобой снова. С момента вашего
последнего личного разговора в основном кейсе произошли новые события (см. контекст выше).
Дай короткую свежую реакцию/мнение на эти новые события от своего лица — это НЕ повтор того,
что ты говорил на общем брифинге, а более личный, неформальный комментарий. 2-4 предложения
(для Уилсона 1-3)."""

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


def call_deepseek(messages: list[dict], model: str, max_tokens: int = 1800) -> str:
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": 0.9, "max_tokens": max_tokens}
    response = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=60)
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
    return "Другие приватные разговоры игрока (для справки, необязательно упоминать):\n" + "\n\n".join(parts)


def build_system_prompt() -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(
        difficulty_instruction=DIFFICULTY_PROMPTS[st.session_state.difficulty],
        forman_desc=PERSONA_DESCRIPTIONS["forman"],
        cameron_desc=PERSONA_DESCRIPTIONS["cameron"],
        chase_desc=PERSONA_DESCRIPTIONS["chase"],
    )


def get_persona_reply(persona_key, model, solo_thread) -> str:
    persona = CHARACTERS[persona_key]
    system = PERSONA_SYSTEM_PROMPT.format(
        name=persona["name"], persona_desc=PERSONA_DESCRIPTIONS[persona_key],
        case_context=build_case_context(),
        other_threads_context=build_other_threads_context(persona_key),
    )
    messages = [{"role": "system", "content": system}] + solo_thread
    return call_deepseek(messages, model, max_tokens=300)


def get_persona_opening(persona_key, model) -> str:
    persona = CHARACTERS[persona_key]
    system = PERSONA_SYSTEM_PROMPT.format(
        name=persona["name"], persona_desc=PERSONA_DESCRIPTIONS[persona_key],
        case_context=build_case_context(),
        other_threads_context=build_other_threads_context(persona_key),
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


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Доктор Хаус: Экономическое отделение", page_icon="🩺")
st.title("🩺 Доктор Хаус: Экономическое отделение")

with st.sidebar:
    st.header("Настройки")
    model_choice = st.selectbox("Модель", options=["deepseek-chat", "deepseek-reasoner"])
    difficulty_label = st.selectbox(
        "Сложность кейса",
        options=["easy", "medium", "hard"],
        format_func=lambda x: {"easy": "Лёгкий — реальный, без маскировки",
                                "medium": "Средний — реальный, замаскированный",
                                "hard": "Сложный — вымышленный"}[x],
    )
    st.divider()
    if st.button("🔄 Новый кейс"):
        for k in ["messages", "solo_threads", "open_panel", "case_symptoms",
                  "symptom_status", "solo_context_len", "solo_collapsed", "dismissed_warnings"]:
            st.session_state.pop(k, None)
        st.session_state.difficulty = difficulty_label
        st.rerun()

defaults = {
    "messages": [], "solo_threads": {}, "open_panel": None, "case_symptoms": [],
    "symptom_status": [], "solo_context_len": {}, "solo_collapsed": {},
    "dismissed_warnings": set(), "difficulty": difficulty_label,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ---------------------------------------------------------------------------
# Старт игры — кнопка вместо ввода ключа
# ---------------------------------------------------------------------------

if not st.session_state.messages:
    st.write("Диагностируй больную экономику. Опрашивай команду, назначай 'анализы', ищи диагноз.")
    if not DEEPSEEK_API_KEY:
        st.error(
            "Ключ DeepSeek не найден. Локально создай файл .streamlit/secrets.toml с строкой "
            'DEEPSEEK_API_KEY = "sk-...". На Streamlit Cloud впиши его в Settings → Secrets.'
        )
        st.stop()
    if st.button("▶️ Начать играть", type="primary"):
        with st.spinner("Готовим первого пациента..."):
            try:
                st.session_state.messages.append({"role": "system", "content": build_system_prompt()})
                reply = call_deepseek(st.session_state.messages, model_choice)
                st.session_state.messages.append({"role": "assistant", "content": reply})
                data = parse_main_response(reply)
                if data["symptoms"]:
                    st.session_state.case_symptoms = data["symptoms"]
                    st.session_state.symptom_status = [False] * len(data["symptoms"])
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

            check = data.get("diagnosis_check", {})
            is_last = (idx == len(st.session_state.messages) - 1)

            if data.get("case_solved"):
                st.success("🏆 Кейс раскрыт!")
            elif check.get("status") == "correct_with_gaps" and is_last and idx not in st.session_state.dismissed_warnings:
                st.warning(
                    f"✅ Диагноз в целом верный, но кое-что упущено:\n\n{check.get('missing_details', '')}"
                )
                c1, c2 = st.columns(2)
                if c1.button("✅ Завершить", key=f"finalize_{idx}"):
                    st.session_state.messages.append({"role": "user", "content": FINALIZE_MESSAGE})
                    with st.spinner("Подводим итоги..."):
                        try:
                            reply = call_deepseek(st.session_state.messages, model_choice)
                            st.session_state.messages.append({"role": "assistant", "content": reply})
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
        if st.session_state.solo_context_len.get(key) != current_len:
            with st.spinner(f"{CHARACTERS[key]['name']} думает..."):
                try:
                    if not st.session_state.solo_threads.get(key):
                        st.session_state.solo_threads[key] = []
                        if key == "wilson":
                            opener = random.choice(WILSON_OPENERS)
                            st.session_state.solo_threads[key].append(
                                {"role": "assistant", "content": f"*{opener}*"}
                            )
                        else:
                            opening = get_persona_opening(key, model_choice)
                            st.session_state.solo_threads[key].append(
                                {"role": "assistant", "content": opening}
                            )
                    else:
                        opening = get_persona_opening(key, model_choice)
                        st.session_state.solo_threads[key].append(
                            {"role": "assistant", "content": opening}
                        )
                    st.session_state.solo_context_len[key] = current_len
                except Exception as e:
                    st.error(f"Ошибка: {e}")

panel = st.session_state.open_panel

# --- Панель "Общее обсуждение" ---
if panel == "general":
    st.caption("⚠️ Сообщение здесь сразу запускает новый общий брифинг команды.")
    general_input = st.chat_input("Твоя мысль для всей команды...")
    if general_input:
        st.session_state.messages.append({"role": "user", "content": general_input})
        with st.spinner("Экономика реагирует..."):
            try:
                reply = call_deepseek(st.session_state.messages, model_choice)
                st.session_state.messages.append({"role": "assistant", "content": reply})
                data = parse_main_response(reply)
                if data.get("symptom_status") and len(data["symptom_status"]) == len(st.session_state.case_symptoms):
                    st.session_state.symptom_status = data["symptom_status"]
                st.session_state.open_panel = None
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка: {e}")

# --- Панель личного разговора ---
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

# --- Обычный ввод в основной брифинг ---
else:
    user_input = st.chat_input("Твой ход (вопрос, гипотеза, назначение анализа...)")
    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.spinner("Экономика реагирует..."):
            try:
                reply = call_deepseek(st.session_state.messages, model_choice)
                st.session_state.messages.append({"role": "assistant", "content": reply})
                data = parse_main_response(reply)
                if data.get("symptom_status") and len(data["symptom_status"]) == len(st.session_state.case_symptoms):
                    st.session_state.symptom_status = data["symptom_status"]
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка: {e}")
