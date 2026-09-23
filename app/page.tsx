import { RecordingUpload } from "@/components/protocol/recording-upload";
import { ServiceStatus } from "@/components/protocol/service-status";

export default function HomePage() {
  return (
    <main className="min-h-screen px-4 py-8 sm:px-6 sm:py-12">
      <div className="mx-auto max-w-5xl">
        <header className="max-w-3xl">
          <p className="text-sm font-medium text-accent">HackAlem AI</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-0.04em] sm:text-6xl">Протокол совещания — без передачи данных в облако</h1>
          <p className="mt-5 text-base leading-7 text-muted sm:text-lg">
            Загружайте запись для локальной обработки русской, казахской и смешанной речи. Аудио, расшифровка и модели остаются на этом компьютере.
          </p>
        </header>

        <div className="mt-10">
          <ServiceStatus />
        </div>

        <div className="mt-6">
          <RecordingUpload />
        </div>

        <section className="mt-6 grid gap-4 text-sm sm:grid-cols-3">
          <article className="rounded-2xl border surface p-5">
            <h2 className="font-semibold">1. Подготовка аудио</h2>
            <p className="mt-2 leading-6 text-muted">FFmpeg приведёт запись к единому безопасному формату для локальной обработки.</p>
          </article>
          <article className="rounded-2xl border surface p-5">
            <h2 className="font-semibold">2. Распознавание и спикеры</h2>
            <p className="mt-2 leading-6 text-muted">Модели запускаются на этом компьютере с выбором MPS или CPU.</p>
          </article>
          <article className="rounded-2xl border surface p-5">
            <h2 className="font-semibold">3. Протокол и поручения</h2>
            <p className="mt-2 leading-6 text-muted">Саммари, поручения и экспорт будут добавлены к локальному конвейеру.</p>
          </article>
        </section>
      </div>
    </main>
  );
}
