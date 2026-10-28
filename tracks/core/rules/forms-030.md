---
id: forms-030
направление: core
категория: формы-xml
серьёзность: критично
платформы: [8.3, 8.5]
заголовок: "Обработчик события группы в Form.form — внутри её extInfo: записанный на уровне группы, он молча выпадает при загрузке в базу"
ключи: [Form.form, handlers, OnCurrentPageChange, ПриСменеСтраницы, PagesGroupExtInfo, UsualGroupExtInfo, GroupExtInfo, обработчик не срабатывает, страницы, закладки]
источник: "ошибка:maERP 2026-10-18, рабочее место производства — ГруппаВерхПриСменеСтраницы не срабатывал с 2.0.15.29; сверено выгрузкой /DumpConfigToFiles формы из базы и моделью формы EDT (handlers есть только у GroupExtInfo)"
check: ["xml-audit:в Form.form у узла items xsi:type=form:FormGroup блок <handlers> прямым потомком группы (после userVisible), а не внутри extInfo — скриптом по формам", "manual:выгрузка формы из базы (DumpConfigToFiles) — у Pages/UsualGroup есть <Events> с этим обработчиком"]
---

# Обработчик группы живёт в её extInfo

## Симптом

Обработчик смены закладки (`OnCurrentPageChange`) объявлен в `Form.form`, процедура в
модуле есть, EDT форму принимает без ошибок, BSL LS не ругается (процедура формально
используется). На клиенте при переключении закладок ничего не происходит. В выгрузке той же
формы из базы (`Form.xml`) у группы `Pages` нет блока `<Events>`.

## Причина

В модели формы EDT события группы — свойство не самой группы (`FormGroup`), а её
расширения: `handlers` есть у `GroupExtInfo` (`PagesGroupExtInfo`, `UsualGroupExtInfo`).
Блок `<handlers>`, записанный рядом с `visible`/`userVisible` — как у полей и таблиц, —
EDT при чтении не сохраняет и в базу не передаёт. Ошибки нет ни на одном шаге.

## Как правильно

```xml
<type>Pages</type>
<extInfo xsi:type="form:PagesGroupExtInfo">
  <handlers>
    <event>OnCurrentPageChange</event>
    <name>ГруппаСтраницыПриСменеСтраницы</name>
  </handlers>
  <pagesRepresentation>TabsOnTop</pagesRepresentation>
</extInfo>
```

У полей, таблиц и кнопок `<handlers>` по-прежнему стоят на уровне самого элемента —
правило только про группы. Новую конструкцию брать с работающего образца (workflow-005),
у которого событие доказанно срабатывает, а не с соседней формы того же автора.
