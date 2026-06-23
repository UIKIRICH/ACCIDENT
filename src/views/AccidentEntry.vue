<template>
  <div class="accident-entry-page">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">事故录入</h1>
        <p class="page-subtitle">录入事故基本信息和相关证据</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-primary" @click="resetForm">
          <span class="btn-icon" v-html="icons.refresh"></span>
          重置
        </button>
      </div>
    </div>

    <div class="entry-form">
      <div class="form-section">
        <div class="section-header">
          <h2 class="section-title">基本信息</h2>
          <span class="section-hint">* 必填项</span>
        </div>
        <div class="form-grid">
          <div class="form-group">
            <label class="form-label">事故类型 <span class="required">*</span></label>
            <select v-model="form.accidentType" class="form-select">
              <option>追尾事故</option>
              <option>变道碰撞</option>
              <option>路口剐蹭</option>
              <option>转弯冲突</option>
              <option>其他</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">发生时间 <span class="required">*</span></label>
            <input v-model="form.time" type="datetime-local" class="form-input">
          </div>
          <div class="form-group">
            <label class="form-label">天气状况</label>
            <select v-model="form.weather" class="form-select">
              <option>晴</option>
              <option>阴</option>
              <option>雨</option>
              <option>雪</option>
              <option>雾</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">道路状况</label>
            <select v-model="form.roadEnv" class="form-select">
              <option>干燥</option>
              <option>潮湿</option>
              <option>结冰</option>
              <option>积水</option>
            </select>
          </div>
          <div class="form-group full-width">
            <label class="form-label">发生地点 <span class="required">*</span></label>
            <div class="location-grid">
              <select v-model="selectedProvince" @change="onProvinceChange" class="form-select">
                <option value="">请选择省份</option>
                <option v-for="province in provinceData" :key="province.name" :value="province.name">{{ province.name }}</option>
              </select>
              <select v-model="selectedCity" @change="onCityChange" class="form-select" :disabled="!selectedProvince">
                <option value="">请选择城市</option>
                <option v-for="city in currentCities" :key="city.name" :value="city.name">{{ city.name }}</option>
              </select>
              <select v-model="selectedDistrict" @change="onDistrictChange" class="form-select" :disabled="!selectedCity">
                <option value="">请选择区县</option>
                <option v-for="district in currentDistricts" :key="district" :value="district">{{ district }}</option>
              </select>
            </div>
            <input :value="form.location" @input="onDetailInput" type="text" class="form-input" placeholder="请输入详细地址（如街道、门牌号等）" style="margin-top: 8px;">
          </div>
        </div>
      </div>

      <div class="form-section">
        <div class="section-header">
          <h2 class="section-title">车辆信息</h2>
          <div class="header-right">
            <span class="vehicle-count" v-if="form.vehicles.length > 0">已添加 {{ form.vehicles.length }} 辆</span>
            <button class="btn btn-sm btn-primary" @click="addVehicle">
              <span class="btn-icon" v-html="icons.plus"></span>
              添加车辆
            </button>
          </div>
        </div>
        <div class="vehicle-info">
          <div class="vehicle-card" v-for="(vehicle, index) in form.vehicles" :key="vehicle.key">
            <div class="vehicle-header">
              <h3 class="vehicle-title">车辆 {{ vehicle.key }}</h3>
              <button class="remove-btn" @click="removeVehicle(index)" title="删除车辆">
                <span v-html="icons.close"></span>
              </button>
            </div>
            <div class="form-grid">
              <div class="form-group">
                <label class="form-label">车辆类型</label>
                <select v-model="vehicle.vehicleType" class="form-select">
                  <option>小型轿车</option>
                  <option>大型客车</option>
                  <option>货车</option>
                  <option>摩托车</option>
                  <option>电动车</option>
                </select>
              </div>
              <div class="form-group">
                <label class="form-label">车牌号</label>
                <input v-model="vehicle.plate" type="text" class="form-input" :placeholder="'如：京' + vehicle.key + '·12345'">
              </div>
              <div class="form-group">
                <label class="form-label">角色</label>
                <select v-model="vehicle.role" class="form-select">
                  <option>前车</option>
                  <option>后车</option>
                  <option>左转车</option>
                  <option>直行车</option>
                  <option>右转车</option>
                  <option>变道车辆</option>
                </select>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="form-section">
        <div class="section-header">
          <h2 class="section-title">事故描述</h2>
        </div>
        <div class="form-group">
          <label class="form-label">详细描述 <span class="required">*</span></label>
          <textarea v-model="form.description" class="form-textarea" rows="5" placeholder="请详细描述事故发生的经过、现场情况等..."></textarea>
        </div>
      </div>

      <div class="form-section">
        <div class="section-header">
          <h2 class="section-title">证据上传</h2>
        </div>
        <div class="upload-area">
          <div class="upload-card" @click="openFolderPicker">
            <div class="upload-icon"><span v-html="icons.folderOpen"></span></div>
            <div class="upload-text">
              <h3>选择文件夹</h3>
              <p>批量选择包含证据的文件夹</p>
            </div>
            <div v-if="form.folderName" class="file-chip">已选择：{{ form.folderName }}</div>
          </div>
          <div class="upload-card" @click="videoInput?.click()">
            <div class="upload-icon"><span v-html="icons.upload"></span></div>
            <div class="upload-text">
              <h3>上传视频</h3>
              <p>支持 MP4、MOV 格式，最大 100MB</p>
            </div>
            <input ref="videoInput" type="file" class="upload-input" accept="video/*" @change="handleVideoUpload">
            <div v-if="form.videoFileName" class="file-chip">已选择：{{ form.videoFileName }}</div>
          </div>
          <div class="upload-card" @click="imageInput?.click()">
            <div class="upload-icon"><span v-html="icons.image"></span></div>
            <div class="upload-text">
              <h3>上传图片</h3>
              <p>支持 JPG、PNG 格式，最大 10MB</p>
            </div>
            <input ref="imageInput" type="file" class="upload-input" accept="image/*" multiple @change="handleImageUpload">
            <div v-if="form.images.length" class="file-chip">{{ form.images.length }} 张图片</div>
          </div>
        </div>
        <div v-if="form.folderName || form.videoFileName || form.images.length" class="uploaded-files">
          <div class="files-header">
            <span class="files-title">已选择的文件</span>
            <button class="clear-btn" @click="clearAllFiles">
              <span v-html="icons.trash"></span>
              清空全部
            </button>
          </div>
          <div class="files-list">
            <div v-if="form.folderName" class="file-item">
              <span class="file-icon folder" v-html="icons.folder"></span>
              <span class="file-name">{{ form.folderName }}</span>
              <button class="file-remove" @click="removeFolder" title="移除">
                <span v-html="icons.close"></span>
              </button>
            </div>
            <div v-if="form.videoFileName" class="file-item">
              <span class="file-icon video" v-html="icons.video"></span>
              <span class="file-name">{{ form.videoFileName }}</span>
              <button class="file-remove" @click="removeVideo" title="移除">
                <span v-html="icons.close"></span>
              </button>
            </div>
            <div v-for="(name, idx) in form.images" :key="idx" class="file-item">
              <span class="file-icon image" v-html="icons.image"></span>
              <span class="file-name">{{ name }}</span>
              <button class="file-remove" @click="removeImage(idx)" title="移除">
                <span v-html="icons.close"></span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="form-actions">
        <div class="nav-buttons-wrapper">
          <button 
            class="nav-btn prev-btn"
            :class="{ disabled: !hasPrev }"
            :disabled="!hasPrev"
            @click="goPrev"
          >
            <span class="btn-icon" v-html="navIcons.chevronLeft"></span>
            <span class="btn-text">上一步</span>
          </button>
          <button 
            class="nav-btn next-btn"
            :class="{ disabled: !hasNext }"
            :disabled="!hasNext"
            @click="goNext"
          >
            <span class="btn-text">下一步</span>
            <span class="btn-icon" v-html="navIcons.chevronRight"></span>
          </button>
        </div>
        <button class="btn btn-primary" @click="saveAsDraft">
          <span class="btn-icon" v-html="icons.save"></span>
          保存草稿
        </button>
        <button class="btn btn-primary" @click="submitAnalysis">
          <span class="btn-icon" v-html="icons.send"></span>
          提交分析
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAccidentFlow } from '../stores/useAccidentFlow'
import { notify } from '../composables/useToast'
import { CasesAPI } from '../api/index.js'

const router = useRouter()
const route = useRoute()
const { state, updateForm, completeIntake, goStep, setCurrentCase, getCurrentCase, isValidCaseId } = useAccidentFlow()
const submitting = ref(false)

// 统一获取 caseId：优先 URL query，fallback store/localStorage，自动过滤无效值
const currentCaseId = () => {
  const queryId = route.query.caseId
  if (isValidCaseId(queryId)) {
    return String(queryId).trim()
  }
  return getCurrentCase()
}

const workflowRoutes = [
  { path: '/overview', name: '首页' },
  { path: '/accident-entry', name: '事故录入' },
  { path: '/video-processing', name: '视频处理' },
  { path: '/image-evidence', name: '图片证据' },
  { path: '/intelligent-analysis', name: '智能分析' },
  { path: '/liability-recommendation', name: '责任建议' },
  { path: '/rule-basis', name: '规则依据' },
  { path: '/manual-review', name: '人工复核' },
  { path: '/history-cases', name: '历史案例' }
]

const navIcons = {
  chevronLeft: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>`,
  chevronRight: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>`
}

const currentIndex = computed(() => {
  return workflowRoutes.findIndex(r => r.path === route.path)
})

const hasPrev = computed(() => {
  return currentIndex.value > 0
})

const hasNext = computed(() => {
  return currentIndex.value < workflowRoutes.length - 1
})

const goPrev = () => {
  if (hasPrev.value) {
    const cid = currentCaseId()
    const path = workflowRoutes[currentIndex.value - 1].path
    router.push(isValidCaseId(cid) ? { path, query: { caseId: cid } } : path)
  }
}

const goNext = () => {
  if (hasNext.value) {
    const cid = currentCaseId()
    const path = workflowRoutes[currentIndex.value + 1].path
    router.push(isValidCaseId(cid) ? { path, query: { caseId: cid } } : path)
  }
}

const form = computed(() => state.form)

// 省市区选择状态
const selectedProvince = ref('')
const selectedCity = ref('')
const selectedDistrict = ref('')
const detailAddress = ref('')

// 省市区数据
const provinceData = [
  {
    name: '北京市',
    cities: [
      { name: '北京市', districts: ['东城区', '西城区', '朝阳区', '丰台区', '石景山区', '海淀区', '门头沟区', '房山区', '通州区', '顺义区', '昌平区', '大兴区', '怀柔区', '平谷区', '密云区', '延庆区'] }
    ]
  },
  {
    name: '天津市',
    cities: [
      { name: '天津市', districts: ['和平区', '河东区', '河西区', '南开区', '河北区', '红桥区', '东丽区', '西青区', '津南区', '北辰区', '武清区', '宝坻区', '滨海新区', '宁河区', '静海区', '蓟州区'] }
    ]
  },
  {
    name: '上海市',
    cities: [
      { name: '上海市', districts: ['黄浦区', '徐汇区', '长宁区', '静安区', '普陀区', '虹口区', '杨浦区', '闵行区', '宝山区', '嘉定区', '浦东新区', '金山区', '松江区', '青浦区', '奉贤区', '崇明区'] }
    ]
  },
  {
    name: '重庆市',
    cities: [
      { name: '重庆市', districts: ['万州区', '涪陵区', '渝中区', '大渡口区', '江北区', '沙坪坝区', '九龙坡区', '南岸区', '北碚区', '綦江区', '大足区', '渝北区', '巴南区', '黔江区', '长寿区', '江津区', '合川区', '永川区', '南川区', '璧山区', '铜梁区', '潼南区', '荣昌区', '开州区', '梁平区', '武隆区'] }
    ]
  },
  {
    name: '河北省',
    cities: [
      { name: '石家庄市', districts: ['长安区', '桥西区', '新华区', '井陉矿区', '裕华区', '藁城区', '鹿泉区', '栾城区', '井陉县', '正定县', '行唐县', '灵寿县', '高邑县', '深泽县', '赞皇县', '无极县', '平山县', '元氏县', '赵县', '辛集市', '晋州市', '新乐市'] },
      { name: '唐山市', districts: ['路南区', '路北区', '古冶区', '开平区', '丰南区', '丰润区', '曹妃甸区', '滦南县', '乐亭县', '迁西县', '玉田县', '遵化市', '迁安市'] },
      { name: '秦皇岛市', districts: ['海港区', '山海关区', '北戴河区', '抚宁区', '青龙满族自治县', '昌黎县', '卢龙县'] }
    ]
  },
  {
    name: '山西省',
    cities: [
      { name: '太原市', districts: ['小店区', '迎泽区', '杏花岭区', '尖草坪区', '万柏林区', '晋源区', '清徐县', '阳曲县', '娄烦县', '古交市'] },
      { name: '大同市', districts: ['新荣区', '平城区', '云冈区', '云州区', '阳高县', '天镇县', '广灵县', '灵丘县', '浑源县', '左云县'] }
    ]
  },
  {
    name: '辽宁省',
    cities: [
      { name: '沈阳市', districts: ['和平区', '沈河区', '大东区', '皇姑区', '铁西区', '苏家屯区', '浑南区', '沈北新区', '于洪区', '辽中区', '康平县', '法库县', '新民市'] },
      { name: '大连市', districts: ['中山区', '西岗区', '沙河口区', '甘井子区', '旅顺口区', '金州区', '普兰店区', '长海县', '瓦房店市', '庄河市'] }
    ]
  },
  {
    name: '吉林省',
    cities: [
      { name: '长春市', districts: ['南关区', '宽城区', '朝阳区', '二道区', '绿园区', '双阳区', '九台区', '农安县', '榆树市', '德惠市', '公主岭市'] },
      { name: '吉林市', districts: ['昌邑区', '龙潭区', '船营区', '丰满区', '永吉县', '蛟河市', '桦甸市', '舒兰市', '磐石市'] }
    ]
  },
  {
    name: '黑龙江省',
    cities: [
      { name: '哈尔滨市', districts: ['道里区', '南岗区', '道外区', '平房区', '松北区', '香坊区', '呼兰区', '阿城区', '双城区', '依兰县', '方正县', '宾县', '巴彦县', '木兰县', '通河县', '延寿县', '尚志市', '五常市'] },
      { name: '齐齐哈尔市', districts: ['龙沙区', '建华区', '铁锋区', '昂昂溪区', '富拉尔基区', '碾子山区', '梅里斯达斡尔族区', '龙江县', '依安县', '泰来县', '甘南县', '富裕县', '克山县', '克东县', '拜泉县', '讷河市'] }
    ]
  },
  {
    name: '江苏省',
    cities: [
      { name: '南京市', districts: ['玄武区', '秦淮区', '建邺区', '鼓楼区', '浦口区', '栖霞区', '雨花台区', '江宁区', '六合区', '溧水区', '高淳区'] },
      { name: '无锡市', districts: ['锡山区', '惠山区', '滨湖区', '梁溪区', '新吴区', '江阴市', '宜兴市'] },
      { name: '徐州市', districts: ['鼓楼区', '云龙区', '贾汪区', '泉山区', '铜山区', '丰县', '沛县', '睢宁县', '新沂市', '邳州市'] },
      { name: '常州市', districts: ['天宁区', '钟楼区', '新北区', '武进区', '金坛区', '溧阳市'] },
      { name: '苏州市', districts: ['姑苏区', '虎丘区', '吴中区', '相城区', '吴江区', '常熟市', '张家港市', '昆山市', '太仓市'] },
      { name: '南通市', districts: ['崇川区', '通州区', '海门区', '如东县', '启东市', '如皋市', '海安市'] }
    ]
  },
  {
    name: '浙江省',
    cities: [
      { name: '杭州市', districts: ['上城区', '下城区', '江干区', '拱墅区', '西湖区', '滨江区', '萧山区', '余杭区', '富阳区', '临安区', '桐庐县', '淳安县', '建德市'] },
      { name: '宁波市', districts: ['海曙区', '江北区', '北仑区', '镇海区', '鄞州区', '奉化区', '象山县', '宁海县', '余姚市', '慈溪市'] },
      { name: '温州市', districts: ['鹿城区', '龙湾区', '瓯海区', '洞头区', '永嘉县', '平阳县', '苍南县', '文成县', '泰顺县', '瑞安市', '乐清市'] }
    ]
  },
  {
    name: '安徽省',
    cities: [
      { name: '合肥市', districts: ['瑶海区', '庐阳区', '蜀山区', '包河区', '长丰县', '肥东县', '肥西县', '庐江县', '巢湖市'] },
      { name: '芜湖市', districts: ['镜湖区', '弋江区', '鸠江区', '三山区', '芜湖县', '繁昌县', '南陵县', '无为市'] }
    ]
  },
  {
    name: '福建省',
    cities: [
      { name: '福州市', districts: ['鼓楼区', '台江区', '仓山区', '马尾区', '晋安区', '长乐区', '闽侯县', '连江县', '罗源县', '闽清县', '永泰县', '平潭县', '福清市'] },
      { name: '厦门市', districts: ['思明区', '海沧区', '湖里区', '集美区', '同安区', '翔安区'] },
      { name: '泉州市', districts: ['鲤城区', '丰泽区', '洛江区', '泉港区', '惠安县', '安溪县', '永春县', '德化县', '金门县', '石狮市', '晋江市', '南安市'] }
    ]
  },
  {
    name: '江西省',
    cities: [
      { name: '南昌市', districts: ['东湖区', '西湖区', '青云谱区', '湾里区', '青山湖区', '新建区', '南昌县', '安义县', '进贤县'] },
      { name: '九江市', districts: ['濂溪区', '浔阳区', '柴桑区', '武宁县', '修水县', '永修县', '德安县', '都昌县', '湖口县', '彭泽县', '瑞昌市', '共青城市', '庐山市'] }
    ]
  },
  {
      name: '山东省',
      cities: [
        { name: '济南市', districts: ['历下区', '市中区', '槐荫区', '天桥区', '历城区', '长清区', '章丘区', '济阳区', '莱芜区', '钢城区', '平阴县', '商河县'] },
        { name: '青岛市', districts: ['市南区', '市北区', '黄岛区', '崂山区', '李沧区', '城阳区', '即墨区', '胶州市', '平度市', '莱西市'] },
        { name: '淄博市', districts: ['淄川区', '张店区', '博山区', '临淄区', '周村区', '桓台县', '高青县', '沂源县'] },
        { name: '枣庄市', districts: ['市中区', '薛城区', '峄城区', '台儿庄区', '山亭区', '滕州市'] },
        { name: '东营市', districts: ['东营区', '河口区', '垦利区', '利津县', '广饶县'] },
        { name: '烟台市', districts: ['芝罘区', '福山区', '牟平区', '莱山区', '蓬莱区', '龙口市', '莱阳市', '莱州市', '招远市', '栖霞市', '海阳市'] },
        { name: '潍坊市', districts: ['潍城区', '寒亭区', '坊子区', '奎文区', '临朐县', '昌乐县', '青州市', '诸城市', '寿光市', '安丘市', '高密市', '昌邑市'] },
        { name: '济宁市', districts: ['任城区', '兖州区', '微山县', '鱼台县', '金乡县', '嘉祥县', '汶上县', '泗水县', '梁山县', '曲阜市', '邹城市'] },
        { name: '泰安市', districts: ['泰山区', '岱岳区', '宁阳县', '东平县', '新泰市', '肥城市'] },
        { name: '威海市', districts: ['环翠区', '文登区', '荣成市', '乳山市'] },
        { name: '日照市', districts: ['东港区', '岚山区', '五莲县', '莒县'] },
        { name: '临沂市', districts: ['兰山区', '罗庄区', '河东区', '沂南县', '郯城县', '沂水县', '兰陵县', '费县', '平邑县', '莒南县', '蒙阴县', '临沭县'] },
        { name: '德州市', districts: ['德城区', '陵城区', '宁津县', '庆云县', '临邑县', '齐河县', '平原县', '夏津县', '武城县', '乐陵市', '禹城市'] },
        { name: '聊城市', districts: ['东昌府区', '阳谷县', '莘县', '茌平区', '东阿县', '冠县', '高唐县', '临清市'] },
        { name: '滨州市', districts: ['滨城区', '沾化区', '惠民县', '阳信县', '无棣县', '博兴县', '邹平市'] },
        { name: '菏泽市', districts: ['牡丹区', '定陶区', '曹县', '单县', '成武县', '巨野县', '郓城县', '鄄城县', '东明县'] }
      ]
    },
  {
    name: '河南省',
    cities: [
      { name: '郑州市', districts: ['中原区', '二七区', '管城回族区', '金水区', '上街区', '惠济区', '中牟县', '巩义市', '荥阳市', '新密市', '新郑市', '登封市'] },
      { name: '开封市', districts: ['龙亭区', '顺河回族区', '鼓楼区', '禹王台区', '祥符区', '杞县', '通许县', '尉氏县', '兰考县'] },
      { name: '洛阳市', districts: ['老城区', '西工区', '瀍河回族区', '涧西区', '吉利区', '洛龙区', '孟津县', '新安县', '栾川县', '嵩县', '汝阳县', '宜阳县', '洛宁县', '伊川县', '偃师市'] }
    ]
  },
  {
    name: '湖北省',
    cities: [
      { name: '武汉市', districts: ['江岸区', '江汉区', '硚口区', '汉阳区', '武昌区', '青山区', '洪山区', '东西湖区', '汉南区', '蔡甸区', '江夏区', '黄陂区', '新洲区'] },
      { name: '黄石市', districts: ['黄石港区', '西塞山区', '下陆区', '铁山区', '阳新县', '大冶市'] }
    ]
  },
  {
    name: '湖南省',
    cities: [
      { name: '长沙市', districts: ['芙蓉区', '天心区', '岳麓区', '开福区', '雨花区', '望城区', '长沙县', '浏阳市', '宁乡市'] },
      { name: '株洲市', districts: ['荷塘区', '芦淞区', '石峰区', '天元区', '渌口区', '攸县', '茶陵县', '炎陵县', '醴陵市'] }
    ]
  },
  {
    name: '广东省',
    cities: [
      { name: '广州市', districts: ['荔湾区', '越秀区', '海珠区', '天河区', '白云区', '黄埔区', '番禺区', '花都区', '南沙区', '从化区', '增城区'] },
      { name: '韶关市', districts: ['武江区', '浈江区', '曲江区', '始兴县', '仁化县', '翁源县', '乳源瑶族自治县', '新丰县', '乐昌市', '南雄市'] },
      { name: '深圳市', districts: ['罗湖区', '福田区', '南山区', '宝安区', '龙岗区', '盐田区', '龙华区', '坪山区', '光明区'] },
      { name: '珠海市', districts: ['香洲区', '斗门区', '金湾区'] },
      { name: '汕头市', districts: ['龙湖区', '金平区', '濠江区', '潮阳区', '潮南区', '澄海区', '南澳县'] },
      { name: '佛山市', districts: ['禅城区', '南海区', '顺德区', '三水区', '高明区'] },
      { name: '东莞市', districts: ['莞城区', '东城区', '南城区', '万江区'] },
      { name: '中山市', districts: ['石岐区', '东区', '西区', '南区', '五桂山区', '火炬开发区'] }
    ]
  },
  {
    name: '海南省',
    cities: [
      { name: '海口市', districts: ['秀英区', '龙华区', '琼山区', '美兰区'] },
      { name: '三亚市', districts: ['海棠区', '吉阳区', '天涯区', '崖州区'] },
      { name: '三沙市', districts: ['西沙区', '南沙区'] },
      { name: '儋州市', districts: ['那大镇', '和庆镇', '南丰镇', '大成镇', '雅星镇', '兰洋镇', '光村镇', '木棠镇', '海头镇', '峨蔓镇', '三都镇', '王五镇', '白马井镇', '中和镇', '排浦镇', '东成镇', '新州镇'] }
    ]
  },
  {
    name: '四川省',
    cities: [
      { name: '成都市', districts: ['锦江区', '青羊区', '金牛区', '武侯区', '成华区', '龙泉驿区', '青白江区', '新都区', '温江区', '双流区', '郫都区', '新津区', '金堂县', '大邑县', '蒲江县', '都江堰市', '彭州市', '邛崃市', '崇州市', '简阳市'] },
      { name: '绵阳市', districts: ['涪城区', '游仙区', '安州区', '三台县', '盐亭县', '梓潼县', '北川羌族自治县', '平武县', '江油市'] },
      { name: '德阳市', districts: ['旌阳区', '罗江区', '中江县', '广汉市', '什邡市', '绵竹市'] }
    ]
  },
  {
    name: '贵州省',
    cities: [
      { name: '贵阳市', districts: ['南明区', '云岩区', '花溪区', '乌当区', '白云区', '观山湖区', '开阳县', '息烽县', '修文县', '清镇市'] },
      { name: '六盘水市', districts: ['钟山区', '水城区', '六枝特区', '盘州市'] }
    ]
  },
  {
    name: '云南省',
    cities: [
      { name: '昆明市', districts: ['五华区', '盘龙区', '官渡区', '西山区', '东川区', '呈贡区', '晋宁区', '富民县', '宜良县', '石林彝族自治县', '嵩明县', '禄劝彝族苗族自治县', '寻甸回族彝族自治县', '安宁市'] },
      { name: '曲靖市', districts: ['麒麟区', '沾益区', '马龙区', '陆良县', '师宗县', '罗平县', '富源县', '会泽县', '宣威市'] }
    ]
  },
  {
    name: '陕西省',
    cities: [
      { name: '西安市', districts: ['新城区', '碑林区', '莲湖区', '灞桥区', '未央区', '雁塔区', '阎良区', '临潼区', '长安区', '高陵区', '鄠邑区', '蓝田县', '周至县'] },
      { name: '铜川市', districts: ['王益区', '印台区', '耀州区', '宜君县'] }
    ]
  },
  {
    name: '甘肃省',
    cities: [
      { name: '兰州市', districts: ['城关区', '七里河区', '西固区', '安宁区', '红古区', '永登县', '皋兰县', '榆中县'] },
      { name: '嘉峪关市', districts: ['雄关区', '长城区', '镜铁区'] }
    ]
  },
  {
    name: '青海省',
    cities: [
      { name: '西宁市', districts: ['城东区', '城中区', '城西区', '城北区', '湟中区', '大通回族土族自治县', '湟源县'] },
      { name: '海东市', districts: ['乐都区', '平安区', '民和回族土族自治县', '互助土族自治县', '化隆回族自治县', '循化撒拉族自治县'] }
    ]
  },
  {
    name: '内蒙古自治区',
    cities: [
      { name: '呼和浩特市', districts: ['新城区', '回民区', '玉泉区', '赛罕区', '土默特左旗', '托克托县', '和林格尔县', '清水河县', '武川县'] },
      { name: '包头市', districts: ['东河区', '昆都仑区', '青山区', '石拐区', '白云鄂博矿区', '九原区', '土默特右旗', '固阳县', '达尔罕茂明安联合旗'] }
    ]
  },
  {
    name: '广西壮族自治区',
    cities: [
      { name: '南宁市', districts: ['兴宁区', '青秀区', '江南区', '西乡塘区', '良庆区', '邕宁区', '武鸣区', '隆安县', '马山县', '上林县', '宾阳县', '横州市'] },
      { name: '柳州市', districts: ['城中区', '鱼峰区', '柳南区', '柳北区', '柳江区', '柳城县', '鹿寨县', '融安县', '融水苗族自治县', '三江侗族自治县'] }
    ]
  },
  {
    name: '西藏自治区',
    cities: [
      { name: '拉萨市', districts: ['城关区', '堆龙德庆区', '达孜区', '林周县', '当雄县', '尼木县', '曲水县', '墨竹工卡县'] },
      { name: '日喀则市', districts: ['桑珠孜区', '南木林县', '江孜县', '定日县', '萨迦县', '拉孜县', '昂仁县', '谢通门县', '白朗县', '仁布县', '康马县', '定结县', '仲巴县', '亚东县', '吉隆县', '聂拉木县', '萨嘎县', '岗巴县'] }
    ]
  },
  {
    name: '宁夏回族自治区',
    cities: [
      { name: '银川市', districts: ['兴庆区', '西夏区', '金凤区', '永宁县', '贺兰县', '灵武市'] },
      { name: '石嘴山市', districts: ['大武口区', '惠农区', '平罗县'] }
    ]
  },
  {
    name: '新疆维吾尔自治区',
    cities: [
      { name: '乌鲁木齐市', districts: ['天山区', '沙依巴克区', '新市区', '水磨沟区', '头屯河区', '达坂城区', '米东区', '乌鲁木齐县'] },
      { name: '克拉玛依市', districts: ['独山子区', '克拉玛依区', '白碱滩区', '乌尔禾区'] }
    ]
  }
]

// 计算属性
const currentCities = computed(() => {
  if (!selectedProvince.value) return []
  const province = provinceData.find(p => p.name === selectedProvince.value)
  return province ? province.cities : []
})

const currentDistricts = computed(() => {
  if (!selectedCity.value) return []
  const city = currentCities.value.find(c => c.name === selectedCity.value)
  return city ? city.districts : []
})

// 事件处理
const onProvinceChange = () => {
  selectedCity.value = ''
  selectedDistrict.value = ''
  updateLocation()
}

const onCityChange = () => {
  selectedDistrict.value = ''
  updateLocation()
}

const onDistrictChange = () => {
  updateLocation()
}

const updateLocation = () => {
  let location = ''
  if (selectedProvince.value) {
    location += selectedProvince.value
  }
  if (selectedCity.value) {
    location += ' ' + selectedCity.value
  }
  if (selectedDistrict.value) {
    location += ' ' + selectedDistrict.value
  }
  if (detailAddress.value) {
    location += ' ' + detailAddress.value
  }
  if (location) {
    updateForm({ location })
  } else {
    updateForm({ location: '' })
  }
}

// 处理详细地址输入
const onDetailInput = (e) => {
  const inputValue = e.target.value
  detailAddress.value = inputValue
  
  // 只组合省市区和详细地址
  let location = ''
  if (selectedProvince.value) {
    location += selectedProvince.value
  }
  if (selectedCity.value) {
    location += ' ' + selectedCity.value
  }
  if (selectedDistrict.value) {
    location += ' ' + selectedDistrict.value
  }
  if (detailAddress.value) {
    location += ' ' + detailAddress.value
  }
  
  updateForm({ location: location || '' })
}

const icons = {
  calendar: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2" fill-opacity="0.15"/><line x1="16" y1="2" x2="16" y2="6" fill="none"/><line x1="8" y1="2" x2="8" y2="6" fill="none"/><line x1="3" y1="10" x2="21" y2="10" fill="none"/></svg>`,
  upload: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" fill="none"/><path d="M17 8l-5-5-5 5" fill="none" stroke-width="2"/><path d="M12 3v12" fill="none" stroke-width="2"/><circle cx="12" cy="18" r="2" fill-opacity="0.3"/></svg>`,
  image: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="3" fill-opacity="0.15"/><circle cx="8.5" cy="8.5" r="2" fill-opacity="0.4"/><path d="M21 15l-5-5-5 5-3-3-5 5" fill="none" stroke-width="1.5"/></svg>`,
  folder: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" fill-opacity="0.2"/></svg>`,
  folderOpen: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" fill-opacity="0.2"/><path d="M2 8h20l-2 11H4L2 8z" fill-opacity="0.1"/></svg>`,
  refresh: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>`,
  plus: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>`,
  close: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`,
  save: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" fill-opacity="0.2"/><polyline points="17 21 17 13 7 13 7 21" fill="none"/><polyline points="7 3 7 8 15 8" fill="none"/></svg>`,
  send: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13" fill="none"/><polygon points="22 2 15 22 11 13 2 9 22 2" fill-opacity="0.2"/></svg>`,
  trash: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>`,
  info: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" fill-opacity="0.2"/><line x1="12" y1="16" x2="12" y2="12" fill="none" stroke-width="2"/><circle cx="12" cy="8" r="0.5" fill-opacity="0.8"/></svg>`,
  video: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="6" width="16" height="12" rx="3" fill-opacity="0.15"/><path d="m22 8-6 4 6 4V8Z" fill-opacity="0.8"/></svg>`
}

const videoInput = ref(null)
const imageInput = ref(null)
let vehicleCounter = 2

const openFolderPicker = () => {
  const input = document.createElement('input')
  input.type = 'file'
  input.webkitdirectory = true
  input.directory = true
  input.multiple = true
  input.onchange = (e) => {
    const files = [...(e.target.files || [])]
    if (files.length > 0) {
      const firstFile = files[0]
      const pathParts = firstFile.webkitRelativePath?.split('/') || []
      const folderName = pathParts[0] || '所选文件夹'
      updateForm({ folderName })
      notify({ title: '文件夹已选择', message: `已选择 ${files.length} 个文件` })
    }
  }
  input.click()
}

const handleVideoUpload = (e) => {
  const file = e.target.files?.[0]
  if (!file) return
  updateForm({ 
    videoFileName: file.name,
    videoFile: file,
    fileName: file.name,
    fileType: 'video',
    fileSize: `${(file.size / 1024 / 1024).toFixed(2)} MB`
  })
  notify({ title: '视频已选择', message: file.name })
}

const handleImageUpload = (e) => {
  const files = [...(e.target.files || [])]
  const imageNames = files.map((f) => f.name)
  const imageFiles = files.map((file) => ({
    file,
    name: file.name,
    preview: URL.createObjectURL(file),
    size: file.size,
    type: file.type
  }))
  const existingImages = state.form.images || []
  const existingImageFiles = state.form.imageFiles || []
  updateForm({ 
    images: [...existingImages, ...imageNames], 
    imageFiles: [...existingImageFiles, ...imageFiles] 
  })
  if (files.length) notify({ title: '图片已选择', message: `已添加 ${files.length} 张图片。` })
}

const removeFolder = () => {
  updateForm({ folderName: '' })
  notify({ title: '已移除', message: '文件夹已从选择中移除' })
}

const removeVideo = () => {
  updateForm({ videoFileName: '' })
  if (videoInput.value) videoInput.value.value = ''
  notify({ title: '已移除', message: '视频已从选择中移除' })
}

const removeImage = (idx) => {
  const images = [...form.value.images]
  const imageFiles = [...form.value.imageFiles]
  const name = images[idx]
  
  // 释放预览URL
  if (imageFiles[idx]?.preview) {
    URL.revokeObjectURL(imageFiles[idx].preview)
  }
  
  images.splice(idx, 1)
  imageFiles.splice(idx, 1)
  updateForm({ images, imageFiles })
  notify({ title: '已移除', message: `${name} 已从选择中移除` })
}

const clearAllFiles = () => {
  // 释放所有图片预览URL
  if (form.value.imageFiles) {
    form.value.imageFiles.forEach(img => {
      if (img.preview) {
        URL.revokeObjectURL(img.preview)
      }
    })
  }
  updateForm({ folderName: '', videoFileName: '', images: [], imageFiles: [] })
  if (videoInput.value) videoInput.value.value = ''
  if (imageInput.value) imageInput.value.value = ''
  notify({ title: '已清空', message: '所有已选择的文件已清空' })
}

const addVehicle = () => {
  vehicleCounter++
  const key = String.fromCharCode(65 + vehicleCounter - 1)
  const vehicles = [...(form.value.vehicles || [])]
  vehicles.push({
    key: key,
    vehicleType: '小型轿车',
    plate: '',
    role: '直行车'
  })
  updateForm({ vehicles })
  notify({ title: '车辆已添加', message: `车辆 ${key} 已添加` })
}

const removeVehicle = (index) => {
  const vehicles = [...(form.value.vehicles || [])]
  const vehicle = vehicles[index]
  vehicles.splice(index, 1)
  updateForm({ vehicles })
  notify({ title: '车辆已删除', message: `车辆 ${vehicle.key} 已删除` })
}

const saveAsDraft = () => {
  notify({ title: '草稿已保存', message: '下次进入页面可继续编辑。' })
}

const resetForm = () => {
  selectedProvince.value = ''
  selectedCity.value = ''
  selectedDistrict.value = ''
  detailAddress.value = ''
  
  // 释放所有图片预览URL
  if (form.value.imageFiles) {
    form.value.imageFiles.forEach(img => {
      if (img.preview) {
        URL.revokeObjectURL(img.preview)
      }
    })
  }
  
  updateForm({
    time: '',
    location: '',
    accidentType: '',
    vehicleType: 'A车 / B车',
    description: '',
    note: '',
    weather: '',
    roadEnv: '',
    fileName: '',
    fileType: '',
    fileSize: '',
    duration: '',
    images: [],
    imageFiles: [],
    videoFileName: '',
    vehicles: [
      { key: 'A', vehicleType: '小型轿车', plate: '', role: '前车' },
      { key: 'B', vehicleType: '小型轿车', plate: '', role: '后车' }
    ]
  })
  vehicleCounter = 2
  if (videoInput.value) videoInput.value.value = ''
  if (imageInput.value) imageInput.value.value = ''
  notify({ title: '已重置', message: '表单已重置为默认状态' })
}

const submitAnalysis = async () => {
  if (!form.value.location || !form.value.time || !form.value.description) {
    notify({ title: '提交失败', message: '请先完善时间、地点和事故描述。', type: 'warning' })
    return
  }
  
  submitting.value = true
  try {
    const result = await CasesAPI.create({
      title: form.value.accidentType || '事故案件',
      accident_type: form.value.accidentType,
      location: form.value.location,
      description: form.value.description,
      weather: form.value.weather,
      road_env: form.value.roadEnv,
      vehicles: form.value.vehicles || [],
      priority: '中'
    })

    if (result.success && result.data) {
      // 更新当前案件 ID 为后端返回的 ID（同步到 store + localStorage）
      setCurrentCase(result.data.id)
      
      // 保存快照到后端
      try {
        await CasesAPI.saveSnapshot(result.data.id, 'accident-entry', {
          form: { ...form.value },
          analysis: {},
          recommendation: {},
          ruleBasis: {},
          manualReview: {}
        })
      } catch (e) {
        console.warn('保存快照失败', e)
      }

      // 流程步进（跳转时携带 caseId，确保后续页面可获取）
      goStep('accident-entry')
      completeIntake()
      router.push({ path: '/video-processing', query: { caseId: result.data.id } })
      notify({ title: '提交成功', message: `${result.data.id} 已提交分析。` })
    } else {
      notify({ title: '提交失败', message: '后端返回异常，请重试。', type: 'error' })
    }
  } catch (err) {
    console.error('提交案件失败:', err)
    notify({ title: '提交失败', message: err.message || '无法连接到服务器', type: 'error' })
  } finally {
    submitting.value = false
  }
}

// 处理从历史案例"继续处理"跳转过来的 caseId
onMounted(async () => {
  const caseId = route.query.caseId
  if (!caseId) return
  try {
    const result = await CasesAPI.get(caseId)
    if (result.success && result.data) {
      const c = result.data
      // 同步到 store + localStorage
      setCurrentCase(c.id)
      updateForm({
        accidentType: c.accident_type || '',
        location: c.location || '',
        time: c.occurred_at || '',
        description: c.description || '',
        weather: c.weather || '',
        roadEnv: c.road_env || '',
        vehicleType: c.vehicle_type || '',
        note: c.note || '',
      })
      notify({ title: '案件已加载', message: `案件 ${caseId} 信息已恢复`, type: 'success' })
    } else {
      // 案件不存在，跳转回历史案例
      notify({ title: '案件不存在', message: `案件 ${caseId} 未找到，请从历史案例选择`, type: 'warning' })
      setTimeout(() => router.push('/history-cases'), 1500)
    }
  } catch (err) {
    console.warn('加载案件失败:', err)
    notify({ title: '加载失败', message: '无法从后端获取案件数据，请重试', type: 'warning' })
    setTimeout(() => router.push('/history-cases'), 2000)
  }
})
</script>

<style scoped>
.accident-entry-page {
  width: 100%;
  min-height: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  padding: var(--space-5);
  animation: pageIn 0.5s cubic-bezier(0.22, 1, 0.36, 1);
  background: linear-gradient(180deg, rgba(59, 130, 246, 0.03) 0%, transparent 100%);
}

@keyframes pageIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-5);
  background: linear-gradient(135deg, var(--bg-primary) 0%, rgba(59, 130, 246, 0.05) 100%);
  border-radius: var(--radius-2xl);
  border: 1px solid var(--border-light);
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.header-content { flex: 1; }

.page-title {
  margin: 0 0 var(--space-2);
  font-size: 28px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.04em;
  background: linear-gradient(135deg, var(--text-primary) 0%, var(--primary) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.page-subtitle {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
  font-weight: 500;
}

.header-actions { display: flex; gap: var(--space-3); }

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: 12px 24px;
  min-height: 44px;
  border-radius: var(--radius-lg);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  border: 1.5px solid transparent;
  font-family: var(--font-sans);
  white-space: nowrap;
}

.btn-sm {
  padding: 10px 18px;
  min-height: 36px;
  font-size: 13px;
}

.btn-icon { width: 18px; height: 18px; }

.btn-primary {
  background: linear-gradient(135deg, var(--primary) 0%, #2563eb 100%);
  color: white;
  box-shadow: 0 4px 14px rgba(59, 130, 246, 0.3);
  border: none;
}

.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 25px rgba(59, 130, 246, 0.45);
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
}

.btn-primary:active {
  transform: translateY(0);
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
}

.btn-secondary {
  background: linear-gradient(135deg, var(--bg-primary) 0%, rgba(59, 130, 246, 0.05) 100%);
  color: var(--text-primary);
  border-color: var(--primary-200);
}

.btn-secondary:hover {
  background: linear-gradient(135deg, var(--primary-soft) 0%, rgba(59, 130, 246, 0.1) 100%);
  color: var(--primary);
  border-color: var(--primary-400);
  transform: translateY(-2px);
  box-shadow: 0 4px 14px rgba(59, 130, 246, 0.15);
}

.btn-secondary:active {
  transform: translateY(0);
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
}

.entry-form {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.form-section {
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-2xl);
  padding: var(--space-5);
  transition: all var(--transition-normal);
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}

.form-section:hover { 
  box-shadow: 0 8px 30px rgba(0,0,0,0.08);
  border-color: var(--primary-200);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-5);
  padding-bottom: var(--space-4);
  border-bottom: 2px solid var(--border-light);
}

.header-right {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.vehicle-count {
  font-size: 13px;
  color: var(--primary);
  font-weight: 600;
  background: rgba(59, 130, 246, 0.1);
  padding: 6px 14px;
  border-radius: var(--radius-full);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.section-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.section-title::before {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(180deg, var(--primary) 0%, #2563eb 100%);
  border-radius: var(--radius-full);
}

.section-hint {
  font-size: 13px;
  color: var(--text-muted);
  font-weight: 500;
}

.required { color: #ef4444; }

.upload-tips {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 13px;
  color: var(--text-secondary);
}

.tip-icon { width: 16px; height: 16px; color: var(--primary); }

.form-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
}

.form-group { display: flex; flex-direction: column; }
.form-group.full-width { grid-column: 1 / -1; }

.location-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-3);
}

.form-label {
  display: block;
  margin-bottom: var(--space-2);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.form-input, .form-select, .form-textarea {
  width: 100%;
  padding: 10px 14px;
  border-radius: var(--radius-lg);
  border: 1.5px solid var(--border-light);
  background: linear-gradient(135deg, var(--bg-primary) 0%, rgba(59, 130, 246, 0.02) 100%);
  color: var(--text-primary);
  font-size: 14px;
  font-family: var(--font-sans);
  transition: all var(--transition-fast);
  outline: none;
  line-height: 1.5;
  cursor: pointer;
}

.form-input:hover, .form-select:hover, .form-textarea:hover {
  border-color: var(--primary-300);
  background: linear-gradient(135deg, var(--bg-primary) 0%, rgba(59, 130, 246, 0.06) 100%);
}

.form-input:focus, .form-select:focus, .form-textarea:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.15), 0 4px 12px rgba(59, 130, 246, 0.1);
  background: var(--bg-primary);
}

.form-select {
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%233b82f6'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  background-size: 20px;
  padding-right: 36px;
}

.form-textarea {
  min-height: 120px;
  resize: vertical;
  line-height: var(--leading-relaxed);
}

input[type="datetime-local"] { font-family: var(--font-sans); color-scheme: light; }
[data-theme='dark'] input[type="datetime-local"] { color-scheme: dark; }

.vehicle-info {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: var(--space-4);
  align-items: start;
}

.vehicle-card {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.04) 0%, rgba(59, 130, 246, 0.02) 100%);
  border: 1.5px solid rgba(59, 130, 246, 0.12);
  border-radius: var(--radius-xl);
  padding: var(--space-5);
  position: relative;
  transition: all var(--transition-normal);
  min-height: 180px;
}

/* 车辆卡片内部表单网格 - 更灵活的响应式 */
.vehicle-card .form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--space-4);
}

.vehicle-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}

.vehicle-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}

.remove-btn {
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1.5px solid rgba(239, 68, 68, 0.2);
  background: linear-gradient(135deg, rgba(239, 68, 68, 0.05) 0%, rgba(239, 68, 68, 0.08) 100%);
  color: #ef4444;
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.remove-btn:hover {
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  color: white;
  border-color: transparent;
  transform: scale(1.08);
  box-shadow: 0 4px 14px rgba(239, 68, 68, 0.35);
}

.remove-btn:active {
  transform: scale(1);
  box-shadow: 0 2px 8px rgba(239, 68, 68, 0.25);
}

.remove-btn span { width: 17px; height: 17px; }

.upload-area {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: var(--space-4);
}

.upload-card {
  border: 2px dashed var(--border-medium);
  border-radius: var(--radius-2xl);
  padding: var(--space-8) var(--space-5);
  text-align: center;
  cursor: pointer;
  background: linear-gradient(135deg, var(--bg-secondary) 0%, rgba(59, 130, 246, 0.02) 100%);
  transition: all var(--transition-normal);
  position: relative;
}

.upload-card:hover {
  border-color: var(--primary-300);
  background: linear-gradient(135deg, var(--primary-soft) 0%, rgba(59, 130, 246, 0.05) 100%);
  transform: translateY(-2px);
  box-shadow: 0 8px 28px rgba(59, 130, 246, 0.12);
}

.upload-icon {
  width: 56px;
  height: 56px;
  margin: 0 auto var(--space-4);
  background: linear-gradient(135deg, var(--primary-soft) 0%, rgba(59, 130, 246, 0.08) 100%);
  border-radius: var(--radius-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary);
  transition: all var(--transition-normal);
}

.upload-card:hover .upload-icon {
  background: linear-gradient(135deg, var(--primary) 0%, #2563eb 100%);
  color: white;
  transform: scale(1.05);
  box-shadow: 0 4px 16px rgba(59, 130, 246, 0.35);
}

.upload-icon span { width: 24px; height: 24px; }

.upload-text h3 {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.upload-text p {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0;
  font-weight: 500;
}

.upload-input { display: none; }

.file-chip {
  margin-top: var(--space-3);
  padding: 6px 14px;
  border-radius: var(--radius-full);
  background: linear-gradient(135deg, var(--primary) 0%, #2563eb 100%);
  color: white;
  font-size: 11px;
  font-weight: 700;
  display: inline-block;
  position: relative;
  z-index: 1;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
}

.uploaded-files {
  margin-top: var(--space-5);
  padding-top: var(--space-5);
  border-top: 2px solid var(--border-light);
}

.files-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}

.files-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-secondary);
}

.clear-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 7px 14px;
  border: 1.5px solid rgba(239, 68, 68, 0.2);
  background: linear-gradient(135deg, rgba(239, 68, 68, 0.03) 0%, rgba(239, 68, 68, 0.06) 100%);
  color: #ef4444;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  border-radius: var(--radius-lg);
  transition: all var(--transition-fast);
  font-family: var(--font-sans);
}

.clear-btn:hover {
  background: linear-gradient(135deg, rgba(239, 68, 68, 0.08) 0%, rgba(239, 68, 68, 0.12) 100%);
  border-color: rgba(239, 68, 68, 0.35);
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(239, 68, 68, 0.15);
}

.clear-btn:active {
  transform: translateY(0);
  box-shadow: 0 1px 4px rgba(239, 68, 68, 0.1);
}

.clear-btn span { width: 15px; height: 15px; }

.files-list { display: flex; flex-direction: column; gap: var(--space-2); }

.file-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  background: linear-gradient(135deg, var(--bg-secondary) 0%, rgba(59, 130, 246, 0.02) 100%);
  border-radius: var(--radius-xl);
  border: 1.5px solid var(--border-light);
  transition: all var(--transition-fast);
}

.file-item:hover {
  border-color: var(--primary-300);
  background: linear-gradient(135deg, var(--primary-soft) 0%, rgba(59, 130, 246, 0.06) 100%);
  transform: translateX(4px);
  box-shadow: 0 4px 14px rgba(59, 130, 246, 0.12);
}

.file-icon {
  width: 38px;
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-lg);
  flex-shrink: 0;
  background: linear-gradient(135deg, var(--primary-soft) 0%, rgba(59, 130, 246, 0.1) 100%);
  color: var(--primary);
  transition: all var(--transition-fast);
}

.file-item:hover .file-icon {
  background: linear-gradient(135deg, var(--primary) 0%, #2563eb 100%);
  color: white;
  transform: scale(1.05);
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.25);
}

.file-icon span { width: 17px; height: 17px; }

.file-name {
  flex: 1;
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-remove {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1.5px solid transparent;
  background: transparent;
  color: var(--text-muted);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.file-remove:hover {
  background: linear-gradient(135deg, rgba(239, 68, 68, 0.08) 0%, rgba(239, 68, 68, 0.12) 100%);
  color: #ef4444;
  border-color: rgba(239, 68, 68, 0.25);
  transform: scale(1.08);
  box-shadow: 0 2px 8px rgba(239, 68, 68, 0.15);
}

.file-remove:active {
  transform: scale(1);
  box-shadow: 0 1px 4px rgba(239, 68, 68, 0.1);
}

.file-remove span { width: 15px; height: 15px; }

.form-actions {
  display: flex;
  gap: var(--space-5);
  justify-content: center;
  padding-top: var(--space-2);
  align-items: center;
}

.nav-buttons-wrapper {
  display: flex;
  gap: var(--space-5);
}

.nav-buttons-wrapper .nav-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-8);
  border-radius: var(--radius-xl);
  border: none;
  cursor: pointer;
  font-size: var(--text-lg);
  font-weight: 600;
  font-family: var(--font-sans);
  transition: all var(--transition-fast);
  min-width: 140px;
}

.nav-buttons-wrapper .prev-btn {
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-light);
}

.nav-buttons-wrapper .prev-btn:hover:not(:disabled) {
  background: var(--bg-secondary);
  border-color: var(--border-color);
}

.nav-buttons-wrapper .next-btn {
  background: var(--primary);
  color: white;
}

.nav-buttons-wrapper .next-btn:hover:not(:disabled) {
  background: var(--primary-dark);
}

.nav-buttons-wrapper .nav-btn.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.nav-buttons-wrapper .btn-icon {
  width: 16px;
  height: 16px;
}

.nav-buttons-wrapper .btn-text {
  line-height: 1;
}


@media (max-width: 1200px) {
  .accident-entry-page { padding: var(--space-4); gap: var(--space-4); }
  .page-header { padding: var(--space-4); }
  .page-title { font-size: 26px; }
  .form-grid { grid-template-columns: repeat(2, 1fr); }
  .vehicle-info { grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
}

@media (max-width: 768px) {
  .accident-entry-page { padding: var(--space-3); gap: var(--space-3); }
  .page-header { 
    flex-direction: column; 
    align-items: stretch; 
    gap: var(--space-3);
    padding: var(--space-4);
  }
  .page-title { font-size: 24px; }
  .header-actions { justify-content: center; }
  .form-grid, .vehicle-info, .upload-area { grid-template-columns: 1fr; }
  .vehicle-card .form-grid { grid-template-columns: 1fr; }
  .form-actions { 
    flex-direction: column; 
    gap: var(--space-3);
  }
  .form-actions .btn { width: 100%; }
}

@media (min-width: 1600px) {
  .vehicle-info { grid-template-columns: repeat(3, 1fr); }
}
</style>