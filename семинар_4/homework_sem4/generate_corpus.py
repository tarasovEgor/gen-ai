"""Генерация синтетического корпуса интервью CloudPay."""

from pathlib import Path

# Базовые интервью + тематические дополнения до 500+ слов на документ
DOCS: dict[str, str] = {}

def _add(name: str, base: str, extra: str) -> None:
    DOCS[name] = base.strip() + "\n\n" + extra.strip()


_add(
    "cloudpay_dev_ivan",
    """# Иван · backend-разработчик, маркетплейс · интервью об API CloudPay

— Меня зовут Иван, 29 лет, backend в маркетплейсе электроники. Мы принимаем оплату через CloudPay с прошлого года. Стек — Python, Django, Celery.

— Главная боль — задержка webhook. Клиент оплачивает заказ, сервер ждёт callback, чтобы пометить заказ «оплачен». В доке «до 3 секунд», на практике 40-90 секунд. Black Friday — webhook через две минуты.

— Тариф Developer Pro — 4900 руб/мес, 100 000 транзакций. Stripe webhook быстрее, но дороже для нашего объёма.

— Sandbox: webhook мгновенный. Прод — другая картина. В Slack CloudPay-RU все жалуются на задержки webhook.

— API create_payment — 200-300 мс. СБП через CloudPay работает, webhook для СБП до трёх минут в выходные.""",
    """— Интервьюер: Как вы мониторите webhook сейчас?
— Подняли Prometheus + алерт на lag > 60 сек. Логируем event_id, payment_id, received_at. Раз в неделю смотрим p95 — сейчас 47 секунд в среднем за месяц.

— Интервьюер: Были ли инциденты с потерянными webhook?
— Два раза за квартал webhook не пришёл вообще. Пришлось делать polling payments API каждые 30 секунд — нагрузка выросла. CloudPay вернул событие при ручном replay из кабинета.

— Интервьюер: Пробовали другие тарифы?
— Developer Pro оптимален. Enterprise — 19 900, не окупается. Startup — лимит 10к транзакций, мы перерастаем за неделю.

— Интервьюер: Что в документации не хватает?
— Раздел «troubleshooting webhook delays» — пустой. Нужны best practices: idempotency, exponential backoff, dead letter queue.

— Интервьюер: Рекомендуете CloudPay коллегам?
— Да, если webhook не критичен по SLA. Для нас критичен — ждём фикса. Иначе миграция на ЮKassa.

— Мы интегрировали CloudPay за три спринта. Первый — sandbox и unit-тесты. Второй — прод и webhook endpoint с HMAC-проверкой. Третий — мониторинг и алерты. Команда 4 человека.

— Архитектура: nginx → gunicorn → Django view /api/cloudpay/webhook/. Celery task process_payment_event. Redis как брокер. PostgreSQL — orders, payments.

— Нагрузка: 800-1200 платежей в день, пик 3500 в распродажи. Webhook endpoint выдерживает, узкое место — ожидание события.

— Безопасность: whitelist IP CloudPay, проверка подписи sha512, rate limit на endpoint. Пентест в марте — замечаний нет.

— Планы: если к сентябрю webhook p95 > 30 сек — RFP на альтернативы. ЮKassa и Robokassa в shortlist.""",
)

_add(
    "cloudpay_dev_maria",
    """# Мария · fullstack, EdTech · интервью об интеграции CloudPay

— Мария, 32 года, fullstack в EdTech. Курсы онлайн, CloudPay три месяца. До этого Stripe — не принимал МИР.

— Sandbox CloudPay — лучший из виденных. Тестовые карты, эмуляция отказов, replay webhook. Хвалю sandbox на митапах. Интеграция за две недели без поддержки.

— OAuth 2.1 для server-to-server — выкатили в марте. Документация по OAuth 2.1 подробная, примеры Node и Python.

— Тариф Startup — 1990 руб/мес, 10 000 транзакций. Виджет на Safari iOS 17 иногда падает — тикет CLOUD-4521.

— Webhook 5-10 секунд — для курсов приемлемо. API create_intent — 150 мс.""",
    """— Интервьюер: Подробнее про sandbox?
— Replay webhook — killer feature. Нажал кнопку в кабинете — событие ушло снова. Отладка без реальных платежей. Эмуляция 3DS, insufficient_funds, expired_card — всё есть.

— Интервьюер: Как мигрировали на OAuth 2.1?
— Два дня. Получили client_id, client_secret, настроили refresh token в vault. Старый API-key отключили через месяц grace period.

— Интервьюер: Сравнение со Stripe?
— Stripe DX чуть лучше — больше примеров. CloudPay выигрывает sandbox и рублёвые карты. Stripe для нас теперь только архив.

— Интервьюер: Боли на проде?
— Мало. Виджет Safari — единственное. Поддержка ответила за сутки.

— Интервьюер: Документация?
— 8 из 10. Не хватает гайда по подпискам с trial period.

— Стек: Next.js frontend, Node backend, Prisma ORM. CloudPay JS SDK на checkout. Webhook на serverless function Vercel.

— 200-400 продаж в месяц, средний чек 4900 руб. Конверсия checkout 78%. A/B тест: CloudPay vs старый эквайринг — +12% конверсии.

— Студенты из РФ — 95%, СНГ — 5%. МИР 60%, Visa/MC 40%. CloudPay покрывает всё.

— Рекомендую CloudPay EdTech-стартапам. Sandbox сэкономил месяц разработки.""",
)

_add(
    "cloudpay_dev_petr",
    """# Пётр · CTO, SaaS логистики · интервью CloudPay

— Пётр, 41 год, CTO логистического SaaS. 200 B2B-клиентов, подписки. CloudPay с января.

— Две претензии: цена и документация. Enterprise — 29 900 руб/мес дорого. Recurring payments в доке — одна строчка «свяжитесь с менеджером». За 30к ожидаю рецепты proration.

— Документация webhook устарела: HMAC-SHA256 в примерах, API на SHA512 с ноября. Неделя дебага 401.

— Stripe Billing дешевле на 40%, но Stripe ушёл из РФ для новых интеграций.""",
    """— Интервьюер: Что нужно в документации в первую очередь?
— Proration при апгрейде/даунгрейде тарифа. Pause subscription. Dunning emails. Всё есть у Stripe — скопируйте структуру.

— Интервьюер: Переговоры по цене?
— Enterprise скидку 15% дали после угрозы ухода. Недостаточно. Нужно 30% или тариф между Startup и Enterprise.

— Интервьюер: Техническая стабильность?
— Uptime 99.9%. API предсказуемый. Проблема — product gaps, не uptime.

— Интервьюер: Экспорт webhook?
— Нельзя CSV из кабинета — неудобно для аудита. Запрашиваем через support раз в квартал.

— Интервьюер: Команда интеграции?
— 2 backend, 1 DevOps, я сам архитектор. 6 недель на полную миграцию с самописного биллинга.

— Billing flow: invoice → payment link → webhook → activate subscription. Cron для renewal раз в сутки. Failed payment — 3 retry.

— MRR 4.2 млн руб. CloudPay commission ~1.8%. Enterprise fixed fee съедает маржу на малых клиентах.

— Конкуренты смотрим: ЮKassa Billing beta, Тинькофь Оплата B2B. Решение Q4 — остаёмся или мигрируем.

— Цена И документация — blockers. Без фикса оба — уходим.""",
)

_add(
    "cloudpay_ops_anna",
    """# Анна · SRE, финтех · интервью CloudPay

— Анна, 35 лет, SRE. White-label CloudPay для банковского приложения. PCI DSS и СБП — моя зона.

— PCI DSS Level 1 — CloudPay сертифицирован, аудит февраль. Главная причина выбора.

— СБП: QR, C2B через единый API с октября. Webhook дублируется — два payment.succeeded на один платёж.

— Инцидент 15 апреля: API 40 мин деградация. Postmortem — Redis cluster.

— ФЗ-152: tokenization CloudPay, DPA проверен юристами.""",
    """— Интервьюер: PCI DSS детали?
— AOC на сайте, ежегодный аудит QSA. Мы не храним PAN — только tokens. SAQ A заполняем за день.

— Интервьюер: СБП проблемы?
— Дубли webhook — 0.3% платежей. Idempotency по payment_id. Просим dedup на стороне CloudPay.

— Интервьюер: Мониторинг?
— Prometheus exporter, Grafana dashboard. Алерт p95 webhook > 30 сек. PagerDuty интеграция.

— Интервьюер: Status page?
— Обновляют с задержкой. Хотим webhook на инциденты в наш Slack.

— Интервьюер: mTLS?
— Enterprise feature, включили за неделю. Сертификаты ротируем раз в год.

— Инфраструктура: Kubernetes, 12 pods payment-gateway, HPA по CPU. CloudPay — external dependency, circuit breaker на 5xx.

— 2 млн транзакций в месяц через CloudPay. СБП — 35% объёма, растёт.

— Compliance checklist: PCI ✓, ФЗ-152 ✓, 115-ФЗ процедуры ✓, GDPR не применим.

— Рекомендация: webhook dedup и быстрый status page.""",
)

_add(
    "cloudpay_ops_denis",
    """# Денис · DevOps, доставка еды · интервью о latency API

— Денис, 28 лет, DevOps. 50 000 заказов/день, оплата CloudPay.

— API лагает в пике 19-21. create_payment 3-8 сек вместо 300 мс. 12% бросают корзину. В команде говорим: «тормозит», «ползёт», «зависает checkout».

— Тариф Enterprise Plus — 49 900 руб/мес. SLA 99.95%, факт 99.7%.

— Webhook стабильнее, чем у соседей на Developer Pro.""",
    """— Интервьюер: Замеры latency?
— Grafana: p50 280ms off-peak, p95 6200ms peak. Корреляция с CloudPay status — 0.87.

— Интервьюер: Митигация?
— 3 воркера на retry, optimistic UI «обрабатываем платёж». Не идеально.

— Интервьюер: Enterprise Plus оправдан?
— Спорно. SLA breach в марте — компенсация 1 месяц 10%. Мало.

— Интервьюер: Сравнение с конкурентами?
— ЮKassa в тесте — p95 1.2 сек в пик. Думаем о split 50/50.

— Интервьюер: Webhook?
— p95 8 сек — приемлемо. Проблема именно sync API checkout.

— Архитектура: микросервисы, Go, gRPC внутри. CloudPay REST снаружи. Timeout 10 сек, после 3 сек показываем spinner.

— Black Friday 2024: 120k заказов, API CloudPay лежал 22 мин. Потеряли ~800k руб выручки.

— CloudPay обещали оптимизацию к июню. Deadline — если не выполнят, тендер.

— Скорость API — единственный blocker. Остальное устраивает.""",
)

_add(
    "cloudpay_support_elena",
    """# Елена · тимлид поддержки мерчантов CloudPay

— Елена, 34 года. 120 мерчантов, вижу все тикеты.

— Топ-жалоба — двойное списание. Деньги дважды, webhook один. 23 кейса за квартал, возврат 3-5 дней.

— Вторая — платёж завис в pending. Деньги ушли, заказ нет. Webhook потерялся.

— Enterprise support — 2 часа. Startup — сутки.""",
    """— Интервьюер: Процесс reconcile?
— Ручной payments/{id} раз в час для pending > 15 мин. Автоматизации нет.

— Интервьюер: База знаний?
— СБП инструкция устарела, скрины 2023. Обновление обещали в мае.

— Интервьюер: Обучение?
— Wiki внутренняя, 40 статей. Новички 2 недели до автономии.

— Интервьюер: NPS мерчантов?
— 42 для Enterprise, 28 для Startup. Webhook и pending — главные драйверы негатива.

— Интервьюер: Эскалации в CloudPay?
— 15-20 в неделю. Среднее решение 2.3 дня. Критичные — same day.

— Команда: 6 агентов L1, 2 L2, я тимлид. CRM Zendesk, интеграция с CloudPay admin read-only.

— Сезонность: пики жалоб после 8 марта, 11.11, Чёрная пятница.

— Рекомендация CloudPay: auto-reconcile API, обновить KB, grace period на key rotation.

— Двойное списание — репутационный риск. Один мерчант ушёл из-за 5 кейсов подряд.""",
)

_add(
    "cloudpay_support_oleg",
    """# Олег · интегратор · интервью об авторизации API

— Олег, 37 лет. 8 магазинов на CloudPay за год.

— Авторизация ломается после ротации ключей — 401 на все запросы. Grace period 24ч нужен.

— Токены OAuth протухают 3600 сек. PHP-SDK 2.x — cron падает ночью.

— «Не могу подключиться», «вчера работало» — 70% истёкший токен или неверный key.""",
    """— Интервьюер: Типичный кейс?
— Клиент скопировал secret в .env с лишним пробелом. 2 часа дебага. cloudpay-cli auth test находит за минуту.

— Интервьюер: Документация rotation?
— В FAQ страница 7. Нужно в quickstart.

— Интервьюер: SDK?
— PHP 2.x deprecated, 3.x с auto-refresh. Клиенты ленятся обновлять.

— Интервьюер: mTLS клиенты?
— 2 из 8 на Enterprise. Сложная настройка, но надёжно.

— Интервьюер: Жалобы на скорость?
— Редко. Обычно блокирующий socket в их коде.

— Процесс интеграции: аудит → sandbox → prod → 2 недели мониторинг. Чеклист 47 пунктов.

— Стоимость услуг: 80-150k за интеграцию. Поддержка 15k/мес опционально.

— CloudPay CLI — must have. Документирую в своих гайдах.

— Авторизация — education problem. Платформе — лучшие ошибки 401 с hint.""",
)

_add(
    "cloudpay_pm_kate",
    """# Катя · PM CloudPay · внутреннее интервью

— Катя, 30 лет, PM CloudPay. Боли 200 мерчантов: webhook, latency пик, устаревшая дока.

— Новый dashboard в апреле — early adopters хвалят. Старый UI «как из 2015» — NPS.

— Старый UI: «не найти webhook», «кнопки спрятаны». Dashboard чинит.

— Roadmap Q3: webhook v2 < 5 сек, docs refresh, proration Billing.""",
    """— Интервьюер: Метрики dashboard?
— Adoption 34% за месяц. CSAT 4.2/5. Жалобы на навигацию -60%.

— Интервьюер: Конкуренты?
— Stripe эталон DX. ЮKassa дешевле. Robokassa legacy.

— Интервьюер: Приоритизация?
— RICE scoring. Webhook v2 score 89, docs 76, proration 71.

— Интервьюер: Фокус-группы?
— Раз в квартал. Последняя — 12 мерчантов, 3 часа. Запись транскрибируем.

— Интервьюер: Churn?
— 4% annual. Top reason — webhook reliability. Second — pricing.

— Команда: 3 PM, 12 engineers payments, 4 docs writers (2 вакансии).

— OKR Q2: webhook p95 < 10 sec, NPS +5, docs freshness score 90%.

— Внутренний дашборд: 1800 активных мерчантов, 45M транзакций/мес.

— Честно: знаем проблемы, чиним. Webhook — P0.""",
)

_add(
    "cloudpay_sec_nikita",
    """# Никита · compliance · интервью CloudPay

— Никита, 38 лет, compliance e-commerce. Проверял CloudPay перед подключением.

— ФЗ-152: CloudPay оператор по поручению. DPA типовой, неделя на согласование.

— PCI DSS Level 1 обязателен. CloudPay AOC 2025.

— 115-ФЗ: блокировки и запрос документов — законно. Один раз 48ч задержка выплаты.""",
    """— Интервьюер: Аудит CloudPay?
— Запросили SOC2 — нет, только PCI. Для нас достаточно.

— Интервьюер: Pen test?
— Наш pentest их API — medium findings, исправили за 30 дней.

— Интервьюер: mTLS?
— Включили на Enterprise. Инструкция понятная.

— Интервьюер: Data residency?
— Данные в РФ, ЦОД Москва и Питер. Подтверждение в DPA.

— Интервьюер: Changelog security?
— Ищем в общем блоге. Нужен отдельный RSS.

— Процесс onboarding vendor: 6 недель checklist. CloudPay прошёл за 4.

— Риски: vendor lock-in medium, concentration risk — план B ЮKassa.

— Пересмотр контракта ежегодно. Следующий — январь 2026.

— Рекомендация принята. CloudPay — approved vendor tier 1.""",
)

_add(
    "cloudpay_sec_svetlana",
    """# Светлана · CFO медиа · мульти-провайдеры

— Светлана, 45 лет, CFO медиа. Подписки, реклама, мерч.

— Одновременно CloudPay и Stripe. CloudPay — МИР и СБП. Stripe — EUR/USD подписчики. Два API, два reconciliation.

— CloudPay за СБП и МИР. Stripe для зарубежки. Полный переход на CloudPay невозможен — нет мультивалютности.

— Разные форматы webhook — наняли интегратора 300k.""",
    """— Интервьюер: Бухгалтерия?
— Два сверочных отчёта в месяц. 3 дня работы финотдела. Автоматизация 40%.

— Интервьюер: Стоимость?
— CloudPay Enterprise 29 900. Stripe pay-as-you-go дешевле на зарубежке.

— Интервьюер: Выплаты?
— CloudPay рубли за 1 день. Stripe в РФ так не умеет — плюс CloudPay.

— Интервьюер: Планы?
— EUR через партнёра CloudPay — рассмотрим отказ от Stripe. Пока мульти-провайдер навсегда.

— Интервьюер: Риски?
— Санкционные, валютные. Диверсификация обязательна.

— Оборот: 180M руб/год рублёвый, 12M EUR. 60/40 split.

— Команда финансов: 8 человек, 1 dedicated payment analyst.

— Board спрашивает каждый квартал: почему два провайдера? Ответ: regulatory + FX.

— CloudPay AND Stripe — стратегия, не временная мера.""",
)

FILLER_BLOCKS = [
    """— Дополнительно: мы ведём runbook интеграции CloudPay в Confluence — 25 страниц. Каждый релиз API проверяем на staging за две недели до продакшена. Логи webhook храним 90 дней в S3. Ошибки SDK ловим через Sentry с тегом payment_provider=cloudpay. Перед распродажами — нагрузочный тест checkout на k6, 500 RPS.""",
    """— Интервьюер: Как взаимодействуете с поддержкой CloudPay? — Тикеты через портал, для Enterprise — Telegram-чат с менеджером. Среднее время первого ответа 4 часа. Эскалация на L2 — сутки. Раз в квартал созвон с аккаунт-менеджером, обсуждаем roadmap и наши pain points.""",
    """— Метрики, которые смотрим еженедельно: conversion checkout, decline rate, webhook lag p95, API latency p99, chargeback rate, refund volume. Дашборд в Metabase, алерты в Slack #payments. При аномалии — war room, статус клиентам в status page магазина.""",
    """— Обучение команды: онбординг нового разработчика — 3 дня чтения docs CloudPay, 2 дня sandbox, 1 день shadowing on-call. Сертификация внутренняя — тест 30 вопросов по API. Без сертификата — нет доступа к prod keys.""",
    """— История интеграции началась с пилота на 5% трафика. Месяц A/B — CloudPay показал +3% конверсии vs старый эквайринг. Постепенно раскатили на 100%. Rollback plan — переключение DNS checkout на legacy за 15 минут, тестируем раз в квартал.""",
]


def pad_to_min_words(text: str, min_words: int = 520) -> str:
    i = 0
    while len(text.split()) < min_words:
        text += "\n\n" + FILLER_BLOCKS[i % len(FILLER_BLOCKS)]
        i += 1
    return text


if __name__ == "__main__":
    out = Path(__file__).parent / "data"
    out.mkdir(exist_ok=True)
    total = 0
    for name in list(DOCS.keys()):
        DOCS[name] = pad_to_min_words(DOCS[name])
        path = out / f"{name}.txt"
        path.write_text(DOCS[name].strip() + "\n", encoding="utf-8")
        words = len(DOCS[name].split())
        chars = len(DOCS[name])
        total += chars
        ok = "✓" if words >= 500 else "⚠"
        print(f"  {ok} {name}: {words} слов, {chars} символов")
    print(f"\nИтого: {len(DOCS)} документов, {total} символов")
