export type MaterialCategory = 'documentation' | 'user_flow'

export interface MaterialGenerationRequest {
  projectId: number
  category: MaterialCategory
  source: 'code' | 'documentation'
}

export interface GeneratedFile {
  name: string
  content: string
  path?: string
}

export interface GeneratedDocumentation {
  files: GeneratedFile[]
}

export interface MaterialGenerator {
  generate(request: MaterialGenerationRequest): Promise<GeneratedDocumentation>
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

  async generate(request: MaterialGenerationRequest): Promise<GeneratedDocumentation> {
    if (this.generator === null) throw new MaterialGeneratorUnavailableError()
    return this.generator.generate(request)
  }
}

export const materialGeneratorRegistry = new MaterialGeneratorRegistry()
