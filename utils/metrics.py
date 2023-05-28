import os
import csv


class Metrics:
    def record_metric(self, *args, **kwargs):
        raise NotImplementedError('record_metric')

    def close(self):
        raise NotImplementedError('close')


class MockMetrics(Metrics):
    def __init__(self):
        super().__init__()

    def record_metric(self, *args, **kwargs):
        pass

    def close(self):
        pass


class CsvMetrics(Metrics):
    def __init__(self, csv_path: str, *titles: str):
        super().__init__()
        os.makedirs(os.path.join('.', os.path.dirname(csv_path)), exist_ok=True)
        self._file = open(csv_path, 'w')
        self._csv = csv.writer(self._file)
        self.record_metric(*titles)

    def record_metric(self, *args, **kwargs):
        formatted_args = []
        for arg in args:
            if isinstance(arg, float):
                formatted_args.append('{0:.10f}'.format(arg))
            else:
                formatted_args.append(arg)
        self._csv.writerow(formatted_args)
        self._file.flush()

    def close(self):
        self._file.close()


class MetricsManager:
    def __init__(self, metrics_dir: str, mock_mode: bool = False):
        self._mock_mode = mock_mode
        self._metrics_dir = metrics_dir

    def init_csv_metrics(self, relative_file_path: str, *titles: str) -> Metrics:
        if self._mock_mode:
            return MockMetrics()
        return CsvMetrics(os.path.join(self._metrics_dir, relative_file_path), *titles)
