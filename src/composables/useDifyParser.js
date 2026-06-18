import { computed, ref } from 'vue'

export function useDifyParser(analysisData) {
  // 解析Dify返回的原始数据
  const parseDifyResult = (difyText) => {
    if (!difyText) return null
    
    try {
      // 首先尝试直接解析JSON
      let parsed = tryParseJson(difyText)
      
      // 如果不是JSON，尝试提取代码块
      if (!parsed) {
        const codeBlock = extractCodeBlock(difyText)
        if (codeBlock) {
          parsed = tryParseJson(codeBlock)
        }
      }
      
      // 如果有嵌套的final字段，尝试解析那个
      if (parsed && parsed.final && typeof parsed.final === 'string') {
        const finalParsed = tryParseJson(extractCodeBlock(parsed.final))
        if (finalParsed) {
          parsed = finalParsed
        }
      }
      
      return parsed
    } catch (error) {
      console.error('[DifyParser] 解析失败:', error)
      return null
    }
  }
  
  // 尝试解析JSON
  const tryParseJson = (str) => {
    if (!str) return null
    try {
      const parsed = JSON.parse(str)
      return typeof parsed === 'object' ? parsed : null
    } catch {
      return null
    }
  }
  
  // 提取代码块
  const extractCodeBlock = (str) => {
    if (!str) return null
    const match = str.match(/```(?:json)?\s*([\s\S]*?)```/i)
    return match ? match[1].trim() : null
  }
  
  // 从解析后的数据中提取责任认定信息
  const extractLiabilityData = (parsed) => {
    if (!parsed) return null
    
    const result = {
      confidence: null,
      evidenceIntegrity: null,
      vehicleLiabilities: [],
      reasoningText: '',
      accidentType: '',
      legalClues: [],
      legalRules: []
    }
    
    // 尝试从常见的字段名中提取
    const possibleFields = {
      confidence: ['confidence', '置信度', '可信度', 'confidence_score'],
      evidenceIntegrity: ['evidenceIntegrity', '证据完整度', 'evidence_completeness'],
      accidentType: ['accident_type', '事故类型', 'type'],
      reasoningText: ['reasoning', '理由', '分析', '分析结论', 'final', '分析总结'],
      legalClues: ['laws', '法规依据', '法律依据', '法规', 'legal_basis', 'rules'],
      legalRules: ['rules', '规则', 'matched_rules']
    }
    
    // 查找置信度
    for (const field of possibleFields.confidence) {
      if (parsed[field] !== undefined) {
        result.confidence = normalizeConfidence(parsed[field])
        break
      }
    }
    
    // 查找证据完整度
    for (const field of possibleFields.evidenceIntegrity) {
      if (parsed[field] !== undefined) {
        result.evidenceIntegrity = normalizeConfidence(parsed[field])
        break
      }
    }
    
    // 查找事故类型
    for (const field of possibleFields.accidentType) {
      if (parsed[field]) {
        result.accidentType = String(parsed[field])
        break
      }
    }
    
    // 查找理由阐述
    for (const field of possibleFields.reasoningText) {
      if (parsed[field] && typeof parsed[field] === 'string') {
        result.reasoningText = parsed[field]
        break
      }
    }
    
    // 提取法规线索
    for (const field of possibleFields.legalClues) {
      if (parsed[field]) {
        result.legalClues = extractLegalClues(parsed[field])
        if (result.legalClues.length > 0) break
      }
    }
    
    // 提取法规规则
    for (const field of possibleFields.legalRules) {
      if (parsed[field]) {
        result.legalRules = extractLegalRules(parsed[field])
        if (result.legalRules.length > 0) break
      }
    }
    
    // 提取车辆责任信息
    result.vehicleLiabilities = extractVehicleLiabilities(parsed)
    
    return result
  }
  
  // 提取车辆责任
  const extractVehicleLiabilities = (parsed) => {
    const liabilities = []
    
    // 尝试多种常见的责任字段
    const liabilityFields = [
      'liability_suggestion', 'liability', '责任', '责任建议', 'liability_result',
      'vehicles', 'vehicle_liabilities', '车辆责任'
    ]
    
    for (const field of liabilityFields) {
      const data = parsed[field]
      if (data) {
        if (Array.isArray(data)) {
          // 数组形式
          data.forEach((item, index) => {
            const liability = parseSingleLiability(item, index)
            if (liability) liabilities.push(liability)
          })
        } else if (typeof data === 'object') {
          // 对象形式
          const liability = parseSingleLiability(data, 0)
          if (liability) liabilities.push(liability)
        }
      }
    }
    
    if (liabilities.length === 0) {
      // 尝试从文本中提取责任信息
      liabilities.push(...extractLiabilityFromText(parsed))
    }
    
    return liabilities
  }
  
  const parseSingleLiability = (item, index) => {
    if (!item) return null
    
    // 尝试从多种可能的字段组合中提取
    const vehicleRole = extractValue(item, ['role', '角色', '车辆角色', 'type', '类型', 'vehicleType', 'vehicle_type'])
    const licensePlate = extractValue(item, ['plate', '车牌号', '车牌', 'license_plate'])
    const liability = extractValue(item, ['liability', '责任', '责任认定', 'responsibility'])
    const percentage = extractValue(item, ['percentage', '比例', 'ratio', 'percent'])
    
    // 映射责任等级
    let liabilityLevel = '无责任'
    if (liability) {
      const liabText = String(liability).toLowerCase()
      if (liabText.includes('主') || liabText.includes('primary')) {
        liabilityLevel = '主责'
      } else if (liabText.includes('次') || liabText.includes('secondary')) {
        liabilityLevel = '次责'
      } else if (liabText.includes('全') || liabText.includes('full')) {
        liabilityLevel = '主责'
      } else if (liabText.includes('同') || liabText.includes('equal')) {
        liabilityLevel = '次责'
      } else if (liabText.includes('无') || liabText.includes('none')) {
        liabilityLevel = '无责'
      }
    }
    
    // 归一化比例
    let normalizedPercentage = percentage
    if (typeof normalizedPercentage === 'string') {
      normalizedPercentage = parseInt(normalizedPercentage.replace(/[^0-9]/g, ''))
    }
    if (isNaN(normalizedPercentage)) {
      normalizedPercentage = 0
    }
    
    return {
      key: String.fromCharCode(65 + index), // A, B, C...
      vehicleType: vehicleRole || `${String.fromCharCode(65 + index)}车`,
      plate: licensePlate || '',
      role: vehicleRole || `${String.fromCharCode(65 + index)}车`,
      liability: liabilityLevel,
      percentage: normalizedPercentage
    }
  }
  
  const extractValue = (obj, keys) => {
    if (!obj || typeof obj !== 'object') return null
    
    for (const key of keys) {
      if (obj[key] !== undefined && obj[key] !== null) {
        return obj[key]
      }
    }
    return null
  }
  
  const normalizeConfidence = (value) => {
    if (typeof value === 'number') {
      return value > 1 ? Math.min(value, 100) : Math.round(value * 100)
    }
    if (typeof value === 'string') {
      const num = parseInt(value.replace(/[^0-9]/g, ''))
      return isNaN(num) ? null : Math.min(num, 100)
    }
    return null
  }
  
  // 提取法规线索
  const extractLegalClues = (data) => {
    const clues = []
    
    if (Array.isArray(data)) {
      data.forEach(item => {
        if (typeof item === 'string') {
          clues.push(item)
        } else if (typeof item === 'object') {
            // 尝试从对象中提取法规信息
            const lawName = extractValue(item, ['law_name', '法规名称', 'name', 'law'])
            const article = extractValue(item, ['article', '条款', '条', 'article_number'])
            const content = extractValue(item, ['content', '内容', 'description', 'rule'])
            
            if (lawName || article || content) {
              let clue = ''
              if (lawName) clue += lawName
              if (article) clue += (lawName ? ' ' : '') + article
              if (content) clue += (clue ? '：' : '') + content
              if (clue) clues.push(clue)
            }
          }
      })
    } else if (typeof data === 'string') {
      // 如果是字符串，尝试用换行或分号分割
      const parts = data.split(/[；;\n\r]/).filter(p => p.trim())
      parts.forEach(part => {
        if (part.trim()) {
          clues.push(part.trim())
        }
      })
    } else if (typeof data === 'object') {
      // 如果是单个对象
      const lawName = extractValue(data, ['law_name', '法规名称', 'name', 'law'])
      const article = extractValue(data, ['article', '条款', '条', 'article_number'])
      const content = extractValue(data, ['content', '内容', 'description', 'rule'])
      
      if (lawName || article || content) {
        let clue = ''
        if (lawName) clue += lawName
        if (article) clue += (lawName ? ' ' : '') + article
        if (content) clue += (clue ? '：' : '') + content
        if (clue) clues.push(clue)
      }
    }
    
    return clues
  }
  
  // 提取法规规则
  const extractLegalRules = (data) => {
    const rules = []
    
    if (Array.isArray(data)) {
      data.forEach((item, index) => {
        if (typeof item === 'object') {
          const rule = parseSingleLegalRule(item, index)
          if (rule) rules.push(rule)
        }
      })
    } else if (typeof data === 'object') {
      const rule = parseSingleLegalRule(data, 0)
      if (rule) rules.push(rule)
    }
    
    return rules
  }
  
  // 解析单个法规规则
  const parseSingleLegalRule = (item, index) => {
    if (!item || typeof item !== 'object') return null
    
    const code = extractValue(item, ['code', '编号', 'rule_code']) || `R-${String(index + 1).padStart(2, '0')}`
    const lawName = extractValue(item, ['law_name', '法规名称', 'name', 'law'])
    const article = extractValue(item, ['article', '条款', '条', 'article_number'])
    const content = extractValue(item, ['content', '内容', 'description', 'rule', 'rule_name'])
    const confidence = extractValue(item, ['confidence', '置信度', 'match_score'])
    
    // 组合名称
    let name = ''
    if (lawName) name += lawName
    if (article) name += (lawName ? ' ' : '') + article
    
    return {
      code,
      name: name || `法规${index + 1}`,
      content: content || '',
      confidence: normalizeConfidence(confidence) || 90
    }
  }
  
  // 完整的解析流程
  const parseAndUpdateStore = (difyText, updateFn) => {
    const parsedJson = parseDifyResult(difyText)
    const liabilityData = extractLiabilityData(parsedJson)
    
    if (liabilityData) {
      const updates = {
        difyAnalysisText: difyText,
        difyResult: parsedJson
      }
      
      // 只有提取到数据时才更新
      if (liabilityData.confidence !== null) {
        updates.confidence = liabilityData.confidence
      }
      if (liabilityData.evidenceIntegrity !== null) {
        updates.evidenceIntegrity = liabilityData.evidenceIntegrity
      }
      if (liabilityData.vehicleLiabilities.length > 0) {
        updates.vehicleLiabilities = liabilityData.vehicleLiabilities
      }
      if (liabilityData.reasoningText) {
        updates.reasoningText = liabilityData.reasoningText
      }
      if (liabilityData.legalClues.length > 0) {
        updates.difyLegalClues = liabilityData.legalClues
      }
      if (liabilityData.legalRules.length > 0) {
        updates.difyLegalRules = liabilityData.legalRules
      }
      
      updateFn(updates)
      return liabilityData
    }
    
    return null
  }
  
  // 判断是否有Dify的真实数据
  const hasDifyRealData = computed(() => {
    return !!(analysisData?.vehicleLiabilities?.length > 0 && analysisData?.confidence)
  })
  
  return {
    parseDifyResult,
    extractLiabilityData,
    parseAndUpdateStore,
    hasDifyRealData
  }
}
