# Источники пакета инструкций: Бухгалтерия предприятия 3.0 (чтение 2026-10-27)

Каждый факт в where_is.md / notes.md / faq.md / objects.md ссылается на номер отсюда. Текст везде пересказан своими
словами (чистая комната по CONTRIBUTING tiny1C); из источников взяты только факты: пути, номера релизов, поведение.
Этот файл в пакет не входит (манифест его не читает, в промпт он не попадает) — он для ревью и PR. Пометка «[проверить]» в файлах пакета значит, что факт источником не подтверждён: в промпт такие строки не идут.

## Внутренние (TinyCIO, перенос 1:1 или опыт)

| № | что | где |
|---|---|---|
| S-0 | промпты Татьяны: cheat-*.md, examples-chips.json, qol-310.md «Где это в 1С», system-full.md, write-pro-320.md, prompts.go noCodeFeatures, каталог записи bp30.json (config, deny_exact) | origin/main services/ai1c-service/internal/{prompts,changes} |
| S-0a | гочи по БП из RULES.md раздела ai1c (2026-10-26): Остатки регистра бухгалтерии группируют по полям выборки; типы БП искать через метаданные — у части вариантов объекта нет; minus по количеству, не по сумме | docs/ai/RULES.md, ai1c |
| S-0b | тексты маршрутов пакета голоса (write.left.payment, write.receipt.payment_route) | changes/fallback_texts.go |

## Внешние (открытые страницы, дата чтения 2026-10-27)

| № | факт | источник |
|---|---|---|
| S-1 | context7: по «1С:Бухгалтерия предприятия» библиотек нет; есть только БСП (/1c-syntax/ssl_3_1), платформенные (1c-dn), 1c-syntax; query-docs по БП — пусто | context7 MCP, запросы resolve-library-id / query-docs |
| S-2 | its.1c.ru: статья metod81 по ДиректБанку — 404; руководство bp8doc (главы «Денежные средства › Кассовые документы», «Складские операции › 6.3 Перемещение товаров», «Прочие операции › 10.1 Ввод операций вручную», «1.10 Функциональность») отдаёт cp1251, оглавление грузится скриптом — текст не извлечён, только названия глав из поисковых сниппетов | https://its.1c.ru/db/bp8doc (content/29, 117, 159, 197) |
| S-3 | загрузка выписки из файла при подключённом ДиректБанке с 3.0.117; пути полного и простого интерфейса; 11.08.2022 | https://buh.ru/news/uchet_nalogi/152714/ |
| S-4 | выписки по валютным счетам через ДиректБанк с 3.0.117; «Ещё › Обмен с банком › Запросить через 1С:ДиректБанк»; 10.08.2022 | https://buh.ru/news/samoe-novoe-v-1s-bukhgalterii-8-zagruzka-vypiski-cherez-1s-direktbank-po-valyutnym-schetam.html |
| S-5 | закрытие месяца пошагово: путь, подготовка, блоки 1–3 → ОСВ → блок 4, цвета ссылки перепроведения, 3.0.144, что проверять после (25/26 без остатков, 20/23/44), типовые ошибки; обновлено 18.04.2025 | https://buhexpert8.ru/obuchenie-1s/1s-buhgalteriya-8-3/zakrytie-mesyatsa-v-1s-8-3-buhgalteriya-poshagovo.html |
| S-6 | «Нарушена последовательность регламентных операций» при закрытии косвенных расходов; обособленные подразделения — блоки 1/3 по каждому, 2/4 в целом; 3.0.108.36 | https://buhexpert8.ru/voprosy/voprosy-1s-buhgalteriya/ne-vypolnyaetsya-reglamentnaya-operatsiya-zakrytie-schetov-kosvennyh-rashodov.html |
| S-7 | Групповое перепроведение: Операции › Сервис; «Все функции» через Сервис › Параметры; перепроводит всё за период; обработка «Перепроведение документов» в Стандартных | https://buhexpert8.ru/1s-buhgalteriya/lajfhaki-dlya-buhgaltera/nastrojki/administrativnye-nastrojki/gruppovoe-pereprovedenie-dokumentov-v-1s-8-3-buhgalteriya-3-0.html |
| S-8 | Операции › Бухгалтерский учёт › Операции, введённые вручную; виды Операция / Сторно документа / Типовая операция | https://buhexpert8.ru/1s-buhgalteriya/lajfhaki-dlya-buhgaltera/putevoditel-po-dokumentam/operatsii/dokument-operatsiya-vvedennaya-vruchnuyu.html |
| S-9 | ЕНС: Операции › Единый налоговый счёт; Главное › Задачи организации; Банк и касса › «Оплатить › Начисленные налоги и взносы»; Отчёты › 1С-Отчётность › Уведомления…; счёт 68.90; уточняющее уведомление не отменяет прежнее; налог к уменьшению минусом; 11.05.2023 | https://buh.ru/articles/documents/167195/ |
| S-10 | Акт сверки: Продажи › Расчёты с контрагентами (полученные — Покупки); электронный формат ФНС с 3.0.131; «В электронном виде», «Заполнить», ЭДО; 21.03.2023 | https://buh.ru/articles/documents/164516/ |
| S-11 | Помощник по учёту НДС: Отчёты › НДС › Отчётность по НДС, также из Закрытия месяца и Списка задач; с 3.0.67.67 перенос вычетов отключён; 25.12.2018 | https://buh.ru/articles/faq/79539 |
| S-12 | книги строятся по регистрам НДСПокупки / НДСПродажи; последовательность и перепроведение; старый путь «Покупки › Ведение книги покупок › Формирование записей книги покупок» (форум) | https://buhexpert8.ru/voprosy/voprosy-1s-buhgalteriya/reglamentnye-operatsii-po-nds.html ; https://nalog-nalog.ru/forum/buhgalterskoe-po/kak-sformirovat-knigu-pokupok-v-1s/ |
| S-13 | вычет автоматом: снять раздельный учёт (учётная политика, «История изменений»), флажок «Отразить вычет НДС в книге покупок» в СФ → Дт 68.02 Кт 19; отчёт — Отчёты › НДС › Книга покупок; КОРП 3.0.121.25, 2022 | https://buhexpert8.ru/voprosy/voprosy-1s-buhgalteriya/formirovanie-knigi-pokupok.html |
| S-14 | Экспресс-проверка: Отчёты › Экспресс-проверка › Настройка; разделы по книгам покупок и продаж | https://buhexpert8.ru/1s-buhgalteriya/lajfhaki-dlya-buhgaltera/pomoshhniki-buhgaltera/servisy-1s/ekspress-proverka-vedeniya-ucheta-po-nds.html |
| S-15 | Счета-фактуры полученные: Покупки › Покупки › Счета-фактуры полученные; «Создать на основании»; виды операций | https://buhexpert8.ru/1s-buhgalteriya/lajfhaki-dlya-buhgaltera/putevoditel-po-dokumentam/nds-putevoditel-po-dokumentam/schet-faktura-poluchennyj/naznachenie-sozdanie-i-vidy-operatsij-dokumenta-schet-faktura-poluchennyj.html |
| S-16 | состав документов раздела «Продажи» (счёт покупателю, реализация, отчёт о розничных продажах, возвраты, корректировка) — группировка сайта, не меню | https://buhexpert8.ru/1s-buhgalteriya/lajfhaki-dlya-buhgaltera/putevoditel-po-dokumentam/prodazhi ; …/sklad ; …/bank-i-kassa |
| S-17 | журнал «Документы по ОС» через «Настройка навигации» раздела ОС и НМА; 3.0.52.36, 22.09.2017 | https://buh.ru/video/1s-bukhgalteriya-8-red-3-0-kak-vyvesti-zhurnal-dokumentov-po-uchetu-osnovnykh-sredstv-video-.html |
| S-18 | Руководителю › Общие показатели › Расчёты с покупателями и поставщиками («Мы должны / Нам должны»); Руководителю › Расчёты с поставщиками › Задолженность поставщикам по договорам | https://buhexpert8.ru/?p=122117 |
| S-19 | Справочники › Покупки и продажи › Контрагенты / Договоры; «Учёт по договорам» в Функциональности (Расчёты); субконто 60; регистр счетов учёта расчётов с приоритетами; 04.09.2019 | https://buh.ru/articles/documents/95173/ |
| S-20 | главы руководства ИТС «Денежные средства › Кассовые документы», «Платежное поручение», «Банковская выписка» (сниппеты поиска) | https://its.1c.ru/db/bp8doc/content/29/hdoc |
| S-21 | НДС на УСН 2026: пороги 20 / 272,5 / 490,5 млн ₽, ставки 5 / 7 / 22 %; «Сравнение режимов налогообложения» в разделе Руководителю; изменено 03.06.2026 | https://buhexpert8.ru/?p=502917 |
| S-22 | Список задач / Задачи организации: Главное, блок на начальной странице; 11.03.2019 | https://buh.ru/articles/documents/83525/ |
| S-23 | Главное › Настройки › Функциональность / Учётная политика / Налоги и отчёты; Администрирование › Настройки программы › Параметры учёта / Проведение документов | https://buhexpert8.ru/obuchenie-1s/1s-buhgalteriya-8-3/nastrojka-1s-8-3-buhgalteriya-3-0-s-nulya.html |
| S-24 | Функциональность: основная / выборочная / полная; поиск по ключевым словам с 3.0.81; снять флажок нельзя, если учёт вёлся | https://buh.ru/video/1s-bukhgalteriya-8-red-3-0-kak-bystro-nayti-nastroyki-funktsionalnosti-video.html ; https://buhexpert8.ru/?p=57391 |
| S-25 | учёт НДС на УСН с 3.0.165; раздел 7 при 5/7 % с 3.0.173; учётная политика по прибыли — Главное › Настройки › Налоги и отчёты | buh.ru (сниппеты поиска по тегу «НДС 5»); https://buhexpert8.ru/1s-buhgalteriya/nalogi/nalog-na-pribyl/osobennosti-nalogovogo-ucheta-v-1s/nalog-na-pribyl-v-1s-8-3-buhgalteriya-poshagovo.html |
| S-26 | дата запрета: Администрирование › Настройки пользователей и прав › Даты запрета изменения (сниппет по ЗУП 3); право «Добавление и изменение даты запрета редактирования»; только полные права; роль «Главный бухгалтер» пункта не видит | https://buhexpert8.ru/?p=74692 ; https://forum.infostart.ru/forum86/topic315238/ |
| S-27 | НДС 22 % с 3.0.186.21; ставка по дате отгрузки; проверка на рабочей дате 01.01.2026 («Персональные настройки › Рабочая дата»); ККТ; 24.04.2026 | https://nalog-nalog.ru/nds/kak-perejti-na-stavku-nds-22-v-1s-buhgalteriya-nn/ |
| S-28 | не закрываются 20/23/25/26: база распределения по подразделению («Оплата труда», «Плановая себестоимость выпуска»), учётная политика, доработки, переход с 2.0 | https://forum.infostart.ru/forum8/topic291721/ ; https://forum.infostart.ru/forum8/topic174750/ ; https://infostart.ru/1c/articles/1235650/ |
| S-29 | настройки закрытия 20/25/26 в учётной политике БУ | https://buhexpert8.ru/voprosy/voprosy-1s-buhgalteriya/uchetnaya-politika-po-bu-nastrojki-zakrytiya-schetov-20-25-26-i-t-p-v-1s.html |
| S-30 | перенос границы последовательности без перепроведения — с 3.0.63.15, роль «Право интерактивного переноса границы последовательности» | https://buhexpert8.ru/?p=27450 |
| S-31 | экспресс-проверка: проверки книги продаж, нумерация СФ | https://buh.ru/articles/documents/46673/ |
| S-32 | «Сверка данных учёта НДС» — сервис с 3.0.40.31, через партнёров 1С | https://buh.ru/news/automation/42487/ ; https://buh.ru/forum/forum18376/topic87581/ |
| S-33 | отчёты по регистрам ЕНС с 3.0.143 — Отчёты › Единый налоговый счёт | https://buh.ru/video/1s-bukhgalteriya-8-red-3-0-kak-sformirovat-otchety-po-registram-ens-video.html |
| S-34 | 3.0.189.29: строка 5б СФ с 01.01.2026, УПД 5.03 по умолчанию, статья ДДС ЕНП, КБК-2026; 3.0.184.26: расчёт нагрузки на 2026 | https://buh.ru/news/vypushchena-versiya-3-0-189-29-konfiguratsii-bukhgalteriya-predpriyatiya-prof-korp-i-bazovaya-.html ; https://buh.ru/news/vypushchena-versiya-3-0-184-26-konfiguratsii-bukhgalteriya-predpriyatiya-prof-korp-i-bazovaya-.html |
| S-35 | операция вручную не пишет КУДиР при УСН (форум, не подтверждено) | https://forum.infostart.ru/forum86/topic233929/ |

## Что искали и не нашли
- официальный пошаговый порядок регламентных операций закрытия месяца и НДС на открытых страницах its.1c.ru (руководство
  закрыто кодировкой/скриптом; metod81 — 404);
- подтверждённые пути разделов Склад, Производство, ОС и НМА (кроме «Документы по ОС» 2017 г.), Зарплата и кадры,
  Продажи › Продажи › …, Отчёты › Стандартные отчёты (названия группы), Персональные настройки (раздел);
- имя конфигурации Базовой версии; имена метаданных Последовательности и регистра счетов учёта расчётов.
