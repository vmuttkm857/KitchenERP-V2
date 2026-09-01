export const erpUnits=['g','kg','斤','片','個','隻','包','盒','箱','ml','L','罐','桶'] as const

export type ErpUnit=(typeof erpUnits)[number]
