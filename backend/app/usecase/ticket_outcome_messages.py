from app.domain.tickets import LocalizedTicketResult

NO_RELEVANT_CONTENT = LocalizedTicketResult(
    en="The project indexes contain no content relevant to this issue.",
    ru="В индексах проекта нет материалов, относящихся к этому обращению.",
    zh="项目索引中没有与此问题相关的内容。",
)
INVALID_REFERENCES = LocalizedTicketResult(
    en="The model did not cite the retrieved evidence.",
    ru="Модель не сослалась на найденные материалы.",
    zh="模型未引用检索到的证据。",
)
INSUFFICIENT_EVIDENCE = LocalizedTicketResult(
    en="There is not enough evidence to answer.",
    ru="Недостаточно данных для ответа.",
    zh="没有足够的证据回答此问题。",
)
RESOLUTION_DISABLED = LocalizedTicketResult(
    en="Automatic resolution is disabled in the Solver profile.",
    ru="В профиле Solver отключено автоматическое решение.",
    zh="Solver 配置中已停用自动解决。",
)
UI_UNCONFIRMED = LocalizedTicketResult(
    en="The current state of the interface could not be confirmed by an observation.",
    ru="Текущее состояние интерфейса не подтверждено наблюдением.",
    zh="未能通过界面观测确认当前状态。",
)
REVIEW_UNCONFIRMED = LocalizedTicketResult(
    en="Review could not verify the proposed answer.",
    ru="При проверке не удалось подтвердить предложенный ответ.",
    zh="复核未能验证建议的答案。",
)
