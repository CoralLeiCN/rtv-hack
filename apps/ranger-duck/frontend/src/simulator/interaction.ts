/** Share automatic and explicit approach requests without restarting physics. */
export class InteractionCoordinator {
  private generation = 0;
  private pending: Promise<void> | null = null;
  phase: 'idle' | 'settling' | 'approaching' = 'idle';
  constructor(private steps: { prepareDuck(): Promise<void>; prepareAnimal(): Promise<void>; approach(): Promise<void> }) {}
  ensure(): Promise<void> {
    if (this.pending) return this.pending;
    const generation = ++this.generation;
    this.phase = 'settling';
    const current = () => {
      if (generation !== this.generation) throw new DOMException('Approach cancelled.', 'AbortError');
    };
    const work = Promise.resolve().then(async () => {
      current();
      await this.steps.prepareDuck();
      current();
      await this.steps.prepareAnimal();
      current();
      this.phase = 'approaching';
      await this.steps.approach();
      current();
    });
    this.pending = work;
    const complete = () => { if (this.pending === work) { this.pending = null; this.phase = 'idle'; } };
    void work.then(complete, complete);
    return work;
  }
  cancel() { this.generation += 1; this.pending = null; this.phase = 'idle'; }
}
