import type { ComponentProps } from 'react'
import { useT } from '../i18n'
import './filePicker.css'

type Props = Omit<ComponentProps<'input'>, 'type' | 'className'> & { selectedFileName?: string }

export default function FilePicker({ selectedFileName, multiple, ...inputProps }: Props) {
  const { t } = useT()

  return (
    <span className="file-picker">
      <span className="file-picker-trigger">
        <input {...inputProps} type="file" multiple={multiple} />
        <span className="btn btn-secondary file-picker-caption" aria-hidden="true">
          {t(multiple ? 'filePicker.chooseFiles' : 'filePicker.chooseFile')}
        </span>
      </span>
      {selectedFileName && <span className="file-picker-name" role="status">{selectedFileName}</span>}
    </span>
  )
}
