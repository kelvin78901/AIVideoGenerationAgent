/** Minimal EventSource stand-in: tests push named events with `emit`. */
export class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly url: string;
  closed = false;
  private listeners = new Map<string, Set<(ev: Event) => void>>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, fn: (ev: Event) => void): void {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)?.add(fn);
  }

  removeEventListener(type: string, fn: (ev: Event) => void): void {
    this.listeners.get(type)?.delete(fn);
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, data?: unknown, id?: number): void {
    const ev =
      data === undefined
        ? new Event(type)
        : new MessageEvent(type, { data: JSON.stringify(data), lastEventId: String(id ?? "") });
    for (const fn of this.listeners.get(type) ?? []) fn(ev);
  }

  static latest(): FakeEventSource {
    const last = FakeEventSource.instances.at(-1);
    if (!last) throw new Error("no EventSource opened");
    return last;
  }
}
