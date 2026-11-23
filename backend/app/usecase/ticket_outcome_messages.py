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
IMPLEMENTATION_UNCONFIRMED = LocalizedTicketResult(
    en="The implementation does not yet confirm the documented behavior. Provide the affected version and the relevant implementation file or entry point.",
    ru="Реализация пока не подтверждает описанное в документации поведение. Укажите версию продукта и соответствующий файл реализации или точку входа.",
    zh="实现尚未证实文档所述的行为。请提供受影响的版本以及相关的实现文件或入口。",
)
LOCAL_FACT_REQUIRED = LocalizedTicketResult(
    en="The cause could not be confirmed. Provide the affected component and version, plus the exact error message or a log excerpt from this occurrence.",
    ru="Причину не удалось подтвердить. Укажите затронутый компонент и его версию, а также приведите точное сообщение об ошибке или отрывок журнала за этот случай.",
    zh="未能确认原因。请提供受影响的组件和版本，以及本次问题的准确错误消息或日志片段。",
)
LOCAL_FACT_REQUEST = LocalizedTicketResult(
    en="Provide the affected component and version, plus the exact error message or a log excerpt from this occurrence.",
    ru="Укажите затронутый компонент и его версию, а также приведите точное сообщение об ошибке или отрывок журнала за этот случай.",
    zh="请提供受影响的组件和版本，以及本次问题的准确错误消息或日志片段。",
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
