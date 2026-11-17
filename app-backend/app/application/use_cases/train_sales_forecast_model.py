from app.application.dto import SalesForecastTrainingResult
from app.application.ports import SalesForecastModelRepository, SalesForecastTrainer


class TrainSalesForecastModel:
    def __init__(self, repository: SalesForecastModelRepository, trainer: SalesForecastTrainer) -> None:
        self._repository = repository
        self._trainer = trainer

    def execute(self) -> SalesForecastTrainingResult:
        evaluation = self._trainer.train(self._repository.list_training_history())
        activated = evaluation.model_mae < evaluation.baseline_mae
        self._repository.save_evaluation(evaluation, activate=activated)
        return SalesForecastTrainingResult(
            version=evaluation.artifact.version,
            training_samples=evaluation.training_samples,
            evaluation_samples=evaluation.evaluation_samples,
            baseline_mae=evaluation.baseline_mae,
            model_mae=evaluation.model_mae,
            activated=activated,
        )
