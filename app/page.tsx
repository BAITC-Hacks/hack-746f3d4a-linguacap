import { ServiceStatus } from "@/components/protocol/service-status";

export default function HomePage() {
  return (
    <main className="min-h-screen px-4 py-8 sm:px-6 sm:py-12">
      <div className="mx-auto max-w-5xl">
        <header className="max-w-3xl">
          <p className="text-sm font-medium text-accent">HackAlem AI</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-0.04em] sm:text-6xl">Протокол совещания — без передачи данных в облако</h1>
          <p className="mt-5 text-base leading-7 text-muted sm:text-lg">
            Локальный сервис подготовлен к обработке русской, казахской и смешанной речи. Следующими этапами будут загрузка записи, распознавание, диаризация и экспорт протокола.
          </p>
        </header>

        <div className="mt-10">
          <ServiceStatus />
        </div>

        <section className="mt-6 grid gap-4 text-sm sm:grid-cols-3">
          <article className="rounded-2xl border surface p-5">
            <h2 className="font-semibold">1. Подготовка аудио</h2>
            <p className="mt-2 leading-6 text-muted">FFmpeg приведёт запись к единому безопасному формату для локальной обработки.</p>
          </article>
          <article className="rounded-2xl border surface p-5">
            <h2 className="font-semibold">2. Распознавание и спикеры</h2>
            <p className="mt-2 leading-6 text-muted">Модели будут запускаться на этом компьютере с выбором MPS или CPU.</p>
          </article>
          <article className="rounded-2xl border surface p-5">
            <h2 className="font-semibold">3. Протокол и поручения</h2>
            <p className="mt-2 leading-6 text-muted">Саммари, поручения и экспорт появятся после подготовки конвейера обработки.</p>
          </article>
        </section>
      </div>
    </main>
  );
}
