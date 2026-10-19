import { useQuery } from '@tanstack/react-query'

import { listMaterials } from '../../api/materials'

/** 资料下拉选项：总结与出题都必须先选资料（契约 §10 / §11），只列解析成功的。 */
export function useMaterialOptions() {
  const { data, isFetching } = useQuery({
    queryKey: ['materials', 'options'],
    queryFn: () => listMaterials({ page: 1, size: 100, parse_status: 'success' }),
  })

  const options = (data?.items ?? []).map((material) => ({
    value: material.id,
    label: material.title,
  }))

  const titleOf = (id: string | null | undefined) =>
    options.find((option) => option.value === id)?.label ?? '—'

  return { options, titleOf, loading: isFetching }
}
