import { ArrowDown, AudioLines, FileText, LockKeyhole, Sparkles } from "lucide-react";

import { RecordingUpload } from "@/components/protocol/recording-upload";
import { ServiceStatus } from "@/components/protocol/service-status";

const steps = [
  { number: "01", title: "Загрузите запись", description: "Аудио или видео совещания" },
  { number: "02", title: "Проверьте текст", description: "Реплики и имена участников" },
  { number: "03", title: "Скачайте протокол", description: "Итоги и поручения в DOCX или PDF" },
];

export default function HomePage() {
  return (
    <main className="app-shell min-h-screen">
      <div className="mx-auto max-w-[1280px] px-5 pb-16 sm:px-8 lg:px-12">
        <header className="flex min-h-20 items-center justify-between gap-4 border-b border-[rgb(var(--border))]">
          <div className="flex items-center gap-3" aria-label="Tuyin">
            <span className="brand-mark flex h-9 w-9 items-center justify-center rounded-xl" aria-hidden="true">
              <AudioLines className="h-5 w-5" strokeWidth={2.2} />
            </span>
            <div className="leading-tight">
              <span className="block text-[15px] font-semibold tracking-[-0.025em]">Tuyin</span>
              <span className="block text-[10px] font-medium uppercase tracking-[0.18em] text-muted">AI протокол</span>
            </div>
          </div>
          <span className="flex items-center gap-2 rounded-full border bg-white/70 px-3 py-2 text-xs font-medium text-muted">
            <LockKeyhole className="h-3.5 w-3.5 text-accent" aria-hidden="true" />
            Обработка на устройстве
          </span>
        </header>

        <div className="grid gap-8 pb-9 pt-11 lg:grid-cols-[minmax(0,1fr)_340px] lg:items-end lg:gap-16 lg:pb-10 lg:pt-14">
          <div className="max-w-[730px]">
            <div className="mb-5 inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-accent">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" />
              Локальное автопротоколирование
            </div>
            <h1 className="text-[clamp(2.8rem,5vw,4.8rem)] font-semibold leading-[1.04] tracking-[-0.065em]">
              Из записи —<br />
              <span className="text-[rgb(var(--muted))]">в протокол.</span>
            </h1>
            <p className="mt-5 max-w-[590px] text-base leading-7 text-muted sm:text-lg sm:leading-8">
              Загрузите встречу, проверьте расшифровку и получите итоги с поручениями. Русская и казахская речь обрабатываются локально.
            </p>
          </div>
          <div className="hidden border-l border-[rgb(var(--border))] pl-7 text-sm leading-6 text-muted lg:block">
            <Sparkles className="mb-4 h-5 w-5 text-accent" strokeWidth={1.8} aria-hidden="true" />
            <p>Один рабочий процесс: запись, проверка реплик, готовый документ.</p>
            <ArrowDown className="mt-5 h-5 w-5 text-[rgb(var(--foreground))]" aria-hidden="true" />
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start">
          <RecordingUpload />
          <aside className="space-y-6">
            <ServiceStatus />
            <section className="rounded-[24px] border surface p-6 sm:p-7" aria-labelledby="steps-title">
              <div className="flex items-center justify-between">
                <h2 id="steps-title" className="text-base font-semibold tracking-[-0.025em]">Как это работает</h2>
                <FileText className="h-4 w-4 text-muted" aria-hidden="true" />
              </div>
              <ol className="mt-6 space-y-0">
                {steps.map((step, index) => (
                  <li key={step.number} className={`flex gap-4 pb-5 ${index < steps.length - 1 ? "mb-5 border-b" : ""}`}>
                    <span className="pt-0.5 text-xs font-semibold text-accent">{step.number}</span>
                    <div>
                      <h3 className="text-sm font-semibold">{step.title}</h3>
                      <p className="mt-1 text-xs leading-5 text-muted">{step.description}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          </aside>
        </div>

        <footer className="mt-12 flex flex-wrap items-center justify-between gap-3 border-t pt-5 text-xs text-muted">
          <span>Tuyin</span>
          <span>Ваши записи и результаты хранятся локально</span>
        </footer>
      </div>
    </main>
  );
}
