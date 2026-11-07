export type MaterialCategory = 'documentation' | 'user_flow'

export interface MaterialGenerationRequest {
  projectId: number
  category: MaterialCategory
  source: 'code' | 'documentation'
}

export interface GeneratedMarkdown {
  name: string
  content: string
}

export interface MaterialGenerator {
  generate(request: MaterialGenerationRequest): Promise<GeneratedMarkdown>
}

export class MaterialGeneratorUnavailableError extends Error {
  constructor() {
    super('No Markdown material generator is registered')
    this.name = 'MaterialGeneratorUnavailableError'
  }
}

class MaterialGeneratorRegistry {
  private generator: MaterialGenerator | null = null

  register(generator: MaterialGenerator): () => void {
    this.generator = generator
    return () => {
      if (this.generator === generator) this.generator = null
    }
  }

  async generate(request: MaterialGenerationRequest): Promise<GeneratedMarkdown> {
    if (this.generator === null) throw new MaterialGeneratorUnavailableError()
    return this.generator.generate(request)
  }
}

export const materialGeneratorRegistry = new MaterialGeneratorRegistry()
