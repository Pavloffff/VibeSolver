from app.domain.repositories.material_generation import MaterialGenerationGateway
from app.domain.repositories.model_providers import ModelProviderRepository
from app.domain.repositories.ticket_localization import TicketLocalizationRepository
from app.domain.tickets import LocalizedTicketResult, TicketNotFoundError, TicketResultTranslations
from app.usecase.ticket_result_localization import (
    TicketResultLocalizationError,
    localize_ticket_result,
    translate_ticket_result_to_english,
)


class TicketLocalizationUsecase:
    def __init__(
        self,
        repository: TicketLocalizationRepository,
        models: ModelProviderRepository,
        gateway: MaterialGenerationGateway,
        timeout_seconds: int,
        max_output_tokens: int,
    ) -> None:
        self._repository = repository
        self._models = models
        self._gateway = gateway
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens

    async def localize(self, ticket_id: int) -> TicketResultTranslations:
        snapshot = await self._repository.load_locked(ticket_id)
        if snapshot is None:
            raise TicketNotFoundError("Ticket not found")
        if snapshot.text is None or not snapshot.text.strip():
            return TicketResultTranslations(localized_result=None)
        cached = snapshot.translations
        if cached.localized_result is not None:
            return TicketResultTranslations(
                localized_result=cached.localized_result,
                english_result=cached.localized_result.en,
            )
        if cached.english_result is not None:
            return cached
        if snapshot.model_id is None:
            return TicketResultTranslations(localized_result=None)
        model = await self._models.get_model(snapshot.model_id)
        if (
            model is None
            or "chat" not in model.capabilities
            or model.status
            not in {
                "available",
                "installed",
            }
        ):
            return TicketResultTranslations(localized_result=None)
        try:
            credentials = await self._models.get_credentials(model.provider_connection_id)
        except RuntimeError:
            return TicketResultTranslations(localized_result=None)
        if credentials is None:
            return TicketResultTranslations(localized_result=None)
        arguments = (
            self._gateway,
            credentials,
            model.provider_model_id,
            self._timeout_seconds,
            self._max_output_tokens,
        )
        localized: LocalizedTicketResult | None
        english: str | None
        try:
            localized, _ = await localize_ticket_result(snapshot.text, None, *arguments)
            english = localized.en
        except TicketResultLocalizationError as exc:
            localized, english = None, exc.english_result
            if english is None:
                try:
                    english = await translate_ticket_result_to_english(snapshot.text, *arguments)
                except TicketResultLocalizationError:
                    return TicketResultTranslations(localized_result=None)
        translations = TicketResultTranslations(localized_result=localized, english_result=english)
        if await self._repository.save_if_current(snapshot, translations):
            return translations
        return TicketResultTranslations(localized_result=None)
