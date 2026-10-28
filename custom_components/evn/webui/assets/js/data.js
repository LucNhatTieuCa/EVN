// Data Management Module
class DataManager {
    constructor() {
        this.monthlyData = null;
        this.dailyData = null;
        this.currentAccount = null;
        this.currentYear = new Date().getFullYear();
        this.currentPeriodFromSensor = null;

        // Discard obsolete browser-only billing-cycle settings.
        try{localStorage.removeItem('billingCycles');}catch(_){}

        // Cấu hình chu kỳ thanh toán theo tài khoản
        this.billingCycles = {
            // Default: đầu tháng đến cuối tháng
            default: { startDay: 1, type: 'calendar' }
        };
    }

    // Load danh sách accounts từ options.json
    async loadAccounts() {
        try {
            const baseUrl = this.getBaseUrl();
            const response = await window.EVNApi.fetch(baseUrl + '/api/npc/options');

            if (!response.ok) {
                throw new Error('Không thể tải danh sách tài khoản từ API');
            }

            const options = await response.json();
            const accounts = JSON.parse(options.accounts_json);

            // Cập nhật billing cycle từ config API (luôn ghi đè)
            accounts.forEach(acc => {
                const startDay = parseInt(acc.ngaydauky) || 1;
                this.billingCycles[acc.customer_id] = {
                    startDay: startDay,
                    type: startDay > 1 ? 'cycle' : 'calendar'
                };
            });

            return accounts;
        } catch (error) {
            console.error('Lỗi tải danh sách tài khoản:', error);
            throw error;
        }
    }

    // Load dữ liệu cho một tài khoản cụ thể
    async loadDataForAccount(account) {
        try {
            const baseUrl = this.getBaseUrl();

            // Load monthly data
            const monthlyResponse = await window.EVNApi.fetch(`${baseUrl}/api/npc/monthly/${account}`);
            if (!monthlyResponse.ok) {
                throw new Error(`Không thể tải dữ liệu hóa đơn cho ${account}`);
            }
            this.monthlyData = await monthlyResponse.json();

            // Load daily data
            const dailyResponse = await window.EVNApi.fetch(`${baseUrl}/api/npc/daily/${account}`);
            if (!dailyResponse.ok) {
                throw new Error(`Không thể tải dữ liệu tiêu thụ cho ${account}`);
            }
            this.dailyData = await dailyResponse.json();

            // Load current period data from sensors
            try {
                const currentResponse = await window.EVNApi.fetch(`${baseUrl}/api/npc/current/${account}`);
                if (currentResponse.ok) {
                    this.currentPeriodFromSensor = await currentResponse.json();
                }
            } catch (err) {
                console.warn('Could not load current period from sensor:', err);
                this.currentPeriodFromSensor = null;
            }

            this.currentAccount = account;
            this.processData();

            return {
                monthlyData: this.monthlyData,
                dailyData: this.dailyData,
                currentPeriodFromSensor: this.currentPeriodFromSensor
            };
        } catch (error) {
            console.error('Lỗi tải dữ liệu:', error);
            throw error;
        }
    }

    // Xử lý và chuẩn hóa dữ liệu
    processData() {
        // Xử lý daily data
        if (this.dailyData && Array.isArray(this.dailyData)) {
            this.dailyData = this.dailyData.filter(day => {
                const raw = day["Điện tiêu thụ (kWh)"];
                if (raw == null || raw === '' || raw === 'Không có dữ liệu') return false;
                const value = typeof raw === 'string' ? Number(raw.replace(',', '.')) : Number(raw);
                if (!Number.isFinite(value) || value < 0) return false;
                day["Điện tiêu thụ (kWh)"] = value;
                return true;
            });

            // Lọc dữ liệu từ một mốc thời gian nếu cần
            const startDate = new Date(1900, 0, 1);
            this.dailyData = this.dailyData.filter(day => {
                if (!day.Ngày) return false;
                const dayDate = new Date(day.Ngày.split('-').reverse().join('-'));
                return dayDate >= startDate;
            });

            // Sắp xếp dữ liệu theo thứ tự thời gian
            this.dailyData.sort((a, b) =>
                new Date(a.Ngày.split('-').reverse().join('-')) -
                new Date(b.Ngày.split('-').reverse().join('-'))
            );
        } else {
            this.dailyData = [];
        }

        // Sắp xếp monthly data
        if (this.monthlyData && this.monthlyData.SanLuong && Array.isArray(this.monthlyData.SanLuong)) {
            this.monthlyData.SanLuong = this.monthlyData.SanLuong.filter(item => {
                const year = this.normalizeYearValue(item.Năm);
                const month = parseInt(item.Tháng, 10);
                if (year === null || Number.isNaN(month)) return false;
                return true;
            }).sort((a, b) => a.Tháng - b.Tháng);
        } else if (this.monthlyData) {
            this.monthlyData.SanLuong = [];
        }

        if (this.monthlyData && this.monthlyData.TienDien && Array.isArray(this.monthlyData.TienDien)) {
            this.monthlyData.TienDien = this.monthlyData.TienDien.filter(item => {
                const year = this.normalizeYearValue(item.Năm);
                const month = parseInt(item.Tháng, 10);
                if (year === null || Number.isNaN(month)) return false;
                return true;
            }).sort((a, b) => a.Tháng - b.Tháng);
        } else if (this.monthlyData) {
            this.monthlyData.TienDien = [];
        }

        // Đảm bảo monthlyData có structure đúng
        if (!this.monthlyData) {
            this.monthlyData = { SanLuong: [], TienDien: [] };
        }
    }    // Lấy dữ liệu theo tháng (hỗ trợ chu kỳ thanh toán)
    getDataByMonth(monthYear) {
        const billingCycle = this.getBillingCycle();

        if (billingCycle.type === 'calendar') {
            // Chu kỳ theo tháng dương lịch (cũ)
            return this.dailyData.filter(day =>
                day.Ngày && day.Ngày.slice(3, 10) === monthYear
            );
        } else if (billingCycle.type === 'cycle' && billingCycle.startDay === 1) {
            // Chu kỳ được cấu hình thủ công từ ngày 1 - xử lý như tháng dương lịch
            return this.dailyData.filter(day =>
                day.Ngày && day.Ngày.slice(3, 10) === monthYear
            );
        } else {
            // Chu kỳ thanh toán tùy chỉnh
            return this.getDataByBillingPeriod(monthYear, billingCycle.startDay);
        }
    }    // Lấy cấu hình chu kỳ thanh toán cho tài khoản hiện tại
    getBillingCycle() {
        const cycle = this.billingCycles[this.currentAccount] || this.billingCycles.default;
        return cycle;
    }

    // Tính ngày đầu kỳ, cuối kỳ theo logic đúng từ NPC
    tinhngaydauky(ngaydauky, today = null) {
        if (today === null) {
            today = new Date();
        }

        const day = today.getDate();
        const month = today.getMonth(); // 0-based (0 = January)
        const year = today.getFullYear();

        let start;

        if (ngaydauky === 1) {
            // Chu kỳ theo tháng dương lịch
            start = new Date(year, month, 1);
        } else {
            // Chu kỳ tùy chỉnh
            if (day < ngaydauky) {
                // Nếu ngày hiện tại < ngày đầu kỳ, lấy tháng trước
                if (month === 0) {
                    // Tháng 1, lùi về tháng 12 năm trước
                    start = new Date(year - 1, 11, ngaydauky);
                } else {
                    start = new Date(year, month - 1, ngaydauky);
                }
            } else {
                // Nếu ngày hiện tại >= ngày đầu kỳ, lấy tháng hiện tại
                start = new Date(year, month, ngaydauky);
            }
        }

        const end = new Date(today);

        // Tính ngày kết thúc kỳ
        let next_month = start.getMonth() + 1;
        let next_year = start.getFullYear();

        if (next_month > 11) {
            next_month = 0;
            next_year += 1;
        }

        let next_start;
        try {
            next_start = new Date(next_year, next_month, ngaydauky);
        } catch (error) {
            // Nếu ngày không hợp lệ (ví dụ: 31/2), lấy ngày cuối tháng
            const lastDayNextMonth = new Date(next_year, next_month + 1, 0).getDate();
            next_start = new Date(next_year, next_month, Math.min(ngaydauky, lastDayNextMonth));
        }

        const end_ky = new Date(next_start.getTime() - 24 * 60 * 60 * 1000); // Trừ 1 ngày
        const prev_end_ky = new Date(start.getTime() - 24 * 60 * 60 * 1000); // Trừ 1 ngày

        return {
            start: start,
            end: end,
            end_ky: end_ky,
            prev_end_ky: prev_end_ky
        };
    }    // Lấy dữ liệu theo chu kỳ thanh toán (từ ngày X tháng này đến ngày X-1 tháng sau)
    getDataByBillingPeriod(monthYear, startDay) {
        const [month, year] = monthYear.split('-').map(Number);

        // FIXED: Tính ngày bắt đầu thực tế của kỳ thanh toán        // monthYear là tháng hiển thị (tháng kết thúc kỳ)        // monthYear là tháng hiển thị (tháng kết thúc kỳ)
        // Cần tìm ngày bắt đầu kỳ để tính đúng
        const endDate = new Date(year, month - 1, startDay - 1); // Ngày kết thúc kỳ (tháng hiện tại)
        const startDate = new Date(year, month - 2, startDay); // Ngày bắt đầu kỳ (tháng trước)

        // Xử lý trường hợp tháng 1 (phải lùi về tháng 12 năm trước)
        if (month === 1) {
            startDate.setFullYear(year - 1);
            startDate.setMonth(11); // Tháng 12 (0-based)
        } const periods = {
            start: startDate,
            end_ky: endDate
        };
        const filteredData = this.dailyData.filter(day => {
            if (!day.Ngày) return false;

            // Chuyển đổi format ngày từ dd-mm-yyyy sang Date object
            const dayDate = new Date(day.Ngày.split('-').reverse().join('-'));

            // Normalize dates to avoid time comparison issues
            const dayDateNormalized = new Date(dayDate.getFullYear(), dayDate.getMonth(), dayDate.getDate());
            const startDateNormalized = new Date(periods.start.getFullYear(), periods.start.getMonth(), periods.start.getDate());
            const endDateNormalized = new Date(periods.end_ky.getFullYear(), periods.end_ky.getMonth(), periods.end_ky.getDate());

            // Kiểm tra xem ngày có nằm trong chu kỳ không
            const isInPeriod = dayDateNormalized >= startDateNormalized && dayDateNormalized <= endDateNormalized;

            return isInPeriod;
        });
        return filteredData;
    }

    // Lấy dữ liệu trong khoảng thời gian
    getDataByDateRange(startDate, endDate) {
        return this.dailyData.filter(day => {
            const dayDate = new Date(day.Ngày.split('-').reverse().join('-'));
            return dayDate >= startDate && dayDate <= endDate && day["Điện tiêu thụ (kWh)"] > 0;
        });
    }

    normalizeYearValue(value) {
        const year = parseInt(value, 10);
        return Number.isNaN(year) ? null : year;
    }

    buildBillingPeriodRange(month, year, billingCycle) {
        if (billingCycle.type === 'calendar' || (billingCycle.type === 'cycle' && billingCycle.startDay === 1)) {
            const start = new Date(year, month - 1, 1);
            const end = new Date(year, month, 0);
            return { start, end };
        }

        const start = new Date(year, month - 2, billingCycle.startDay);
        const end = new Date(year, month - 1, billingCycle.startDay - 1);

        return { start, end };
    }

    buildPeriodSummaryForMonth(aggregatedMonthlyData, month, year) {
        const billingCycle = this.getBillingCycle();
        const entry = aggregatedMonthlyData.SanLuong.find(item =>
            this.normalizeYearValue(item.Năm) === year && parseInt(item.Tháng, 10) === month
        );
        if (!entry) {
            return null;
        }

        const costEntry = aggregatedMonthlyData.TienDien.find(item =>
            this.normalizeYearValue(item.Năm) === year && parseInt(item.Tháng, 10) === month
        );
        const consumption = typeof entry["Điện tiêu thụ (KWh)"] === 'number'
            ? entry["Điện tiêu thụ (KWh)"]
            : parseFloat(entry["Điện tiêu thụ (KWh)"]) || 0;
        const cost = costEntry
            ? (typeof costEntry["Tiền Điện"] === 'number'
                ? costEntry["Tiền Điện"]
                : parseFloat(costEntry["Tiền Điện"]) || 0)
            : 0;
        const periodRange = this.buildBillingPeriodRange(month, year, billingCycle);

        return {
            month,
            year,
            consumption,
            cost,
            days: null,
            isCurrentPeriod: false,
            period: {
                start: periodRange.start,
                end: periodRange.end
            },
            details: {
                subtotal: null,
                tax: null
            }
        };
    }

    getMonthlyAggregation(filterYear = null) {
        const targetYear = this.normalizeYearValue(filterYear);
        const monthlyData = this.monthlyData || { SanLuong: [], TienDien: [] };
        const monthlyMap = new Map();

        // Aggregate from daily data first (covers all years)
        if (this.dailyData && Array.isArray(this.dailyData)) {
            this.dailyData.forEach(day => {
                if (!day.Ngày) return;
                const dayDate = new Date(day.Ngày.split('-').reverse().join('-'));
                if (Number.isNaN(dayDate.getTime())) return;

                const year = dayDate.getFullYear();
                if (targetYear !== null && year !== targetYear) return;

                const month = dayDate.getMonth() + 1;
                const key = `${year}-${month}`;
                const value = typeof day["Điện tiêu thụ (kWh)"] === 'number'
                    ? day["Điện tiêu thụ (kWh)"]
                    : parseFloat(day["Điện tiêu thụ (kWh)"]) || 0;

                const entry = monthlyMap.get(key) || {
                    Tháng: month,
                    Năm: year,
                    consumption: 0
                };

                entry.consumption += value;
                monthlyMap.set(key, entry);
            });
        }

        // Add monthly data if daily data missing for that month
        if (monthlyData.SanLuong && Array.isArray(monthlyData.SanLuong)) {
            monthlyData.SanLuong.forEach(item => {
                const year = this.normalizeYearValue(item.Năm);
                if (year === null) return;
                if (targetYear !== null && year !== targetYear) return;

                const month = parseInt(item.Tháng, 10);
                const key = `${year}-${month}`;
                const consumption = typeof item["Điện tiêu thụ (KWh)"] === 'number'
                    ? item["Điện tiêu thụ (KWh)"]
                    : parseFloat(item["iện tiêu thụ (KWh)"]) || 0;

                if (!monthlyMap.has(key)) {
                    monthlyMap.set(key, {
                        Tháng: month,
                        Năm: year,
                        consumption
                    });
                } else {
                    const existing = monthlyMap.get(key);
                    if (existing) {
                        existing.consumption = consumption;
                        monthlyMap.set(key, existing);
                    }
                }
            });
        }

        const costMap = new Map();
        if (monthlyData.TienDien && Array.isArray(monthlyData.TienDien)) {
            monthlyData.TienDien.forEach(item => {
                const year = this.normalizeYearValue(item.Năm);
                if (year === null) return;
                if (targetYear !== null && year !== targetYear) return;

                const month = parseInt(item.Tháng, 10);
                const key = `${year}-${month}`;
                const cost = typeof item["Tiền Điện"] === 'number'
                    ? item["Tiền Điện"]
                    : parseFloat(item["Tiền Điện"]) || 0;
                costMap.set(key, cost);
            });
        }

        const sortedEntries = Array.from(monthlyMap.values()).sort((a, b) => {
            if (a.Năm !== b.Năm) {
                return a.Năm - b.Năm;
            }
            return a.Tháng - b.Tháng;
        });

        const SanLuong = [];
        const TienDien = [];

        sortedEntries.forEach(entry => {
            const key = `${entry.Năm}-${entry.Tháng}`;
            const monthlyCost = costMap.has(key)
                ? costMap.get(key)
                : null;

            SanLuong.push({
                Tháng: entry.Tháng,
                Năm: entry.Năm,
                "Điện tiêu thụ (KWh)": entry.consumption
            });

            TienDien.push({
                Tháng: entry.Tháng,
                Năm: entry.Năm,
                "Tiền Điện": monthlyCost
            });
        });

        return { SanLuong, TienDien };
    }

    // Tính toán thống kê tổng quan (bao gồm kỳ hiện tại)
    calculateSummary(filterYear = null) {
        // Đảm bảo monthlyData có structure đúng
        if (!this.monthlyData) {
            this.monthlyData = { SanLuong: [], TienDien: [] };
        }
        if (!this.monthlyData.TienDien) {
            this.monthlyData.TienDien = [];
        }
        if (!this.monthlyData.SanLuong) {
            this.monthlyData.SanLuong = [];
        }

        // Đảm bảo dailyData là array
        if (!this.dailyData || !Array.isArray(this.dailyData)) {
            this.dailyData = [];
        }

        const aggregatedMonthlyData = this.getMonthlyAggregation(filterYear);
        let filteredTienDien = aggregatedMonthlyData.TienDien;
        let filteredSanLuong = aggregatedMonthlyData.SanLuong;
        let filteredDailyData = this.dailyData;

        const targetYear = this.normalizeYearValue(filterYear);

        if (targetYear !== null) {
            filteredDailyData = this.dailyData.filter(day => {
                if (!day.Ngày) return false;
                const year = parseInt(day.Ngày.split('-')[2]);
                return year === targetYear;
            });
        }

        // Tổng tiền điện
        const totalCost = filteredTienDien.reduce((sum, item) => {
            const value = item["Tiền Điện"] || 0;
            return sum + (typeof value === 'number' ? value : parseFloat(value) || 0);
        }, 0);

        // Trung bình hàng tháng
        const monthCount = filteredSanLuong.length;
        const avgMonthlyCost = monthCount > 0
            ? totalCost / (filteredTienDien.filter(item => item["Tiền Điện"] !== null && item["Tiền Điện"] !== undefined).length || 1)
            : 0;

        // Tổng và trung bình tiêu thụ hàng tháng
        const totalMonthlyConsumption = filteredSanLuong.reduce((sum, item) => {
            const value = item["Điện tiêu thụ (KWh)"] || 0;
            return sum + (typeof value === 'number' ? value : parseFloat(value) || 0);
        }, 0);
        const avgMonthlyConsumption = monthCount > 0
            ? totalMonthlyConsumption / monthCount
            : 0;

        // Trung bình hàng ngày
        const validDailyData = filteredDailyData.filter(day => {
            const value = day["Điện tiêu thụ (kWh)"];
            return value && (typeof value === 'number' ? value > 0 : parseFloat(value) > 0);
        });
        const totalDailyConsumption = validDailyData.reduce((sum, day) => {
            const value = day["Điện tiêu thụ (kWh)"];
            return sum + (typeof value === 'number' ? value : parseFloat(value) || 0);
        }, 0);
        const avgDailyConsumption = validDailyData.length > 0
            ? totalDailyConsumption / validDailyData.length
            : 0;

        // Tính toán kỳ hiện tại (chỉ khi đang xem năm hiện tại hoặc tất cả)
        const currentYear = new Date().getFullYear();
        const includeCurrentPeriod = targetYear === null || targetYear === currentYear;
        let currentPeriod = null;
        if (includeCurrentPeriod) {
            currentPeriod = this.calculateCurrentPeriod();
        }

        return {
            totalCost,
            avgMonthlyCost,
            avgMonthlyConsumption,
            avgDailyConsumption,
            totalMonthlyConsumption,
            currentPeriod // Thêm dữ liệu kỳ hiện tại
        };
    }    // Thiết lập chu kỳ thanh toán cho tài khoản
    setBillingCycle(account, startDay, type = 'cycle') {
        this.billingCycles[account] = { startDay, type };
    }

    // Lấy thông tin chu kỳ thanh toán hiện tại
    getCurrentBillingInfo() {
        const cycle = this.getBillingCycle();
        if (cycle.type === 'calendar') {
            return {
                type: 'Theo tháng dương lịch',
                description: 'Từ đầu tháng đến cuối tháng'
            };
        } else if (cycle.type === 'cycle' && cycle.startDay === 1) {
            return {
                type: 'Theo chu kỳ thanh toán',
                description: 'Theo chu kỳ thanh toán',
                startDay: cycle.startDay
            };
        } else {
            return {
                type: 'Theo chu kỳ thanh toán',
                description: 'Theo chu kỳ thanh toán',
                startDay: cycle.startDay
            };
        }
    }

    // Lấy base URL cho Ingress hoặc Static Path
    getBaseUrl() {
        const ingressMatch = window.location.pathname.match(/\/api\/hassio_ingress\/[^\/]+/);
        if (ingressMatch) return ingressMatch[0];

        const staticMatch = window.location.pathname.match(/\/npc-monitor/);
        if (staticMatch) return ''; // When served via static path, APIs should be relative to root

        return '';
    }    // Lấy các tháng duy nhất từ dữ liệu (hỗ trợ chu kỳ thanh toán)
    getUniqueMonths(filterYear = null) {
        const billingCycle = this.getBillingCycle();

        // Đảm bảo dailyData là array
        if (!this.dailyData || !Array.isArray(this.dailyData) || this.dailyData.length === 0) {
            console.warn('⚠️ getUniqueMonths: No daily data available');
            // Nếu không có daily data, thử lấy từ monthly data
            if (this.monthlyData && this.monthlyData.SanLuong && this.monthlyData.SanLuong.length > 0) {
                let months = this.monthlyData.SanLuong.map(item => {
                    const month = item.Tháng.toString().padStart(2, '0');
                    const year = this.normalizeYearValue(item.Năm) || new Date().getFullYear();
                    return `${month}-${year}`;
                });

                // Lọc theo năm nếu có
                const targetYear = this.normalizeYearValue(filterYear);
                if (targetYear !== null) {
                    months = months.filter(m => m.endsWith(`-${targetYear}`));
                }

                return months.sort((a, b) => {
                    const [m1, y1] = a.split('-');
                    const [m2, y2] = b.split('-');
                    return new Date(y2, m2 - 1) - new Date(y1, m1 - 1);
                });
            }
            return [];
        }

        // Lọc dailyData theo năm nếu có
        let filteredDailyData = this.dailyData;
        const targetYear = this.normalizeYearValue(filterYear);
        if (targetYear !== null) {
            filteredDailyData = this.dailyData.filter(day => {
                if (!day.Ngày) return false;
                const year = parseInt(day.Ngày.split('-')[2]);
                return year === targetYear;
            });
        }

        if (billingCycle.type === 'calendar') {
            // Chu kỳ theo tháng dương lịch (cũ)
            const uniqueMonths = [...new Set(filteredDailyData.map(day => day.Ngày?.slice(3, 10)).filter(Boolean))];
            const result = uniqueMonths.sort((a, b) =>
                new Date(b.split('-').reverse().join('-')) -
                new Date(a.split('-').reverse().join('-'))
            );
            return result;
        } else if (billingCycle.type === 'cycle' && billingCycle.startDay === 1) {
            // Chu kỳ được cấu hình thủ công từ ngày 1 - xử lý như tháng dương lịch nhưng với "Kỳ này"
            const uniqueMonths = [...new Set(filteredDailyData.map(day => day.Ngày.slice(3, 10)))];
            const sortedMonths = uniqueMonths.sort((a, b) =>
                new Date(b.split('-').reverse().join('-')) -
                new Date(a.split('-').reverse().join('-'))
            );

            // Thay tháng hiện tại thành "Kỳ này" nếu có và không lọc theo năm
            if (!filterYear) {
                const currentDate = new Date();
                const currentMonthYear = `${(currentDate.getMonth() + 1).toString().padStart(2, '0')}-${currentDate.getFullYear()}`;
                const currentIndex = sortedMonths.indexOf(currentMonthYear);


                if (currentIndex !== -1) {
                    // Thay thế tháng hiện tại bằng "Kỳ này"
                    sortedMonths[currentIndex] = currentMonthYear; // Giữ nguyên format để logic khác hoạt động
                }
            }

            return sortedMonths;
        } else {
            // Chu kỳ thanh toán tùy chỉnh - tạo danh sách kỳ thanh toán
            const result = this.generateBillingPeriods(billingCycle.startDay, filteredDailyData);
            return result;
        }
    }// Tạo danh sách các kỳ thanh toán từ dữ liệu có sẵn
    generateBillingPeriods(startDay, filteredDailyData = null) {
        // Sử dụng filteredDailyData nếu có, nếu không thì dùng this.dailyData
        const dataToUse = filteredDailyData || this.dailyData;

        // Đảm bảo dailyData là array
        if (!dataToUse || !Array.isArray(dataToUse) || dataToUse.length === 0) {
            console.warn('⚠️ generateBillingPeriods: No daily data available');
            return [];
        }

        // Lấy ngày đầu tiên và cuối cùng từ dữ liệu
        const dates = dataToUse
            .map(day => {
                if (!day.Ngày) return null;
                try {
                    return new Date(day.Ngày.split('-').reverse().join('-'));
                } catch (e) {
                    return null;
                }
            })
            .filter(Boolean)
            .sort((a, b) => a - b);

        if (dates.length === 0) return [];

        const firstDate = dates[0];
        const lastDate = dates[dates.length - 1];
        const today = new Date();

        const periods = [];

        // Bắt đầu từ ngày hiện tại và đi ngược về quá khứ
        let currentDate = new Date(today);
        let iterationCount = 0;

        while (currentDate >= firstDate && iterationCount < 24) {
            iterationCount++;

            // Tính chu kỳ thanh toán cho ngày hiện tại
            const periods_info = this.tinhngaydauky(startDay, currentDate);

            // Kiểm tra xem có phải kỳ hiện tại không (kỳ chứa ngày hôm nay)
            const isCurrentPeriod = today >= periods_info.start && today <= periods_info.end_ky;

            // Xử lý kỳ nếu:
            // 1. Có dữ liệu trong kỳ, HOẶC  
            // 2. Là kỳ hiện tại (luôn hiển thị kỳ hiện tại dù chưa có đủ dữ liệu)
            const shouldIncludePeriod = periods_info.start <= lastDate || isCurrentPeriod;

            if (shouldIncludePeriod) {                // Kiểm tra xem chu kỳ này có dữ liệu không
                const hasDataInPeriod = dataToUse.some(day => {
                    const dayDate = new Date(day.Ngày.split('-').reverse().join('-'));
                    return dayDate >= periods_info.start && dayDate <= periods_info.end_ky;
                });

                // Thêm kỳ nếu có dữ liệu HOẶC là kỳ hiện tại
                if (hasDataInPeriod || isCurrentPeriod) {                    // Logic hiển thị tháng theo chuẩn EVN:
                    // Kỳ thanh toán được đặt tên theo tháng kết thúc (tháng hóa đơn)
                    // VD: Kỳ 10/6 → 9/7 = "Kỳ tháng 7" vì hóa đơn phát hành tháng 7
                    let displayMonth, displayYear;

                    if (isCurrentPeriod && startDay === 1) {
                        // Kỳ hiện tại và bắt đầu từ ngày 1: luôn dùng tháng hiện tại
                        displayMonth = today.getMonth() + 1;
                        displayYear = today.getFullYear();
                    } else if (startDay === 1) {
                        // Chu kỳ theo tháng dương lịch (không phải kỳ hiện tại): dùng tháng bắt đầu
                        displayMonth = periods_info.start.getMonth() + 1;
                        displayYear = periods_info.start.getFullYear();
                    } else {
                        // Chu kỳ tùy chỉnh: dùng tháng kết thúc (tháng hóa đơn)
                        displayMonth = periods_info.end_ky.getMonth() + 1;
                        displayYear = periods_info.end_ky.getFullYear();
                    }

                    const periodLabel = `${displayMonth.toString().padStart(2, '0')}-${displayYear}`;

                    if (!periods.includes(periodLabel)) {
                        periods.push(periodLabel);
                    }
                }
            }

            // Lùi về tháng trước
            currentDate.setMonth(currentDate.getMonth() - 1);
        }

        // Đã sắp xếp từ mới nhất đến cũ nhất rồi
        return periods;
    }

    // Tính trend cho summary cards theo chu kỳ thanh toán
    calculateTrendData(recentMonths) {
        const billingCycle = this.getBillingCycle();
        const today = new Date();

        // Ưu tiên dữ liệu từ sensor, nếu không có thì tính toán
        const sensorData = this.currentPeriodFromSensor;

        return recentMonths.map((monthYear, index) => {
            const monthNum = monthYear.split('-')[0];
            const isCurrentPeriod = index === 0; // Kỳ đầu tiên là kỳ hiện tại

            // Nếu là kỳ hiện tại, sử dụng dữ liệu từ sensor
            if (isCurrentPeriod) {
                // Lấy dữ liệu chi tiết cho min/max/avg từ dailyData
                const periodInfo = this.tinhngaydauky(billingCycle.startDay, today);
                const detailData = this.dailyData.filter(d => {
                    if (!d.Ngày || d["Điện tiêu thụ (kWh)"] <= 0) return false;
                    const dayDate = new Date(d.Ngày.split('-').reverse().join('-'));
                    return dayDate >= periodInfo.start && dayDate <= today;
                });

                let min = 0, max = 0, avg = 0, minDay = '', maxDay = '';
                let trend = 'flat', trendValue = 0, trendPercent = 0, badge = '';
                let sparkline = '';

                // Sử dụng dữ liệu từ sensor nếu có
                let totalConsumption = 0;
                let monthlyCost = 0;

                // BẮT BUỘC lấy từ sensor
                if (sensorData) {
                    totalConsumption = sensorData.tieu_thu_ky_nay || 0;
                    monthlyCost = sensorData.tien_dien_ky_nay;
                } else {
                    console.warn('⚠️ No sensor data available for current period!');
                }

                if (detailData.length > 0) {
                    const values = detailData.map(d => d["Điện tiêu thụ (kWh)"]);
                    min = Math.min(...values);
                    max = Math.max(...values);
                    avg = values.reduce((a, b) => a + b, 0) / values.length;
                    minDay = detailData.find(d => d["Điện tiêu thụ (kWh)"] === min)?.Ngày || '';
                    maxDay = detailData.find(d => d["Điện tiêu thụ (kWh)"] === max)?.Ngày || '';

                    // Tính trend cho kỳ hiện tại so với kỳ trước đó
                    if (recentMonths.length > 1) {
                        const prevMonthYear = recentMonths[1];
                        let prevArr;

                        if (billingCycle.type === 'calendar' || (billingCycle.type === 'cycle' && billingCycle.startDay === 1)) {
                            prevArr = this.dailyData.filter(d =>
                                d.Ngày && d.Ngày.slice(3, 10) === prevMonthYear && d["Điện tiêu thụ (kWh)"] > 0
                            );
                        } else {
                            prevArr = this.getDataByBillingPeriod(prevMonthYear, billingCycle.startDay)
                                .filter(d => d["Điện tiêu thụ (kWh)"] > 0);
                        }

                        const prevAvg = prevArr.length > 0 ?
                            prevArr.map(d => d["Điện tiêu thụ (kWh)"]).reduce((a, b) => a + b, 0) / prevArr.length : 0;

                        if (prevAvg > 0 && avg > 0) {
                            trendValue = avg - prevAvg;
                            trendPercent = (trendValue / prevAvg) * 100;

                            if (trendValue > 0.01) trend = 'up';
                            else if (trendValue < -0.01) trend = 'down';

                            if (trendPercent > 20) badge = '<span class="trend-badge">Tăng mạnh</span>';
                            else if (trendPercent < -20) badge = '<span class="trend-badge">Giảm mạnh</span>';
                        }
                    }

                    // Tạo sparkline SVG
                    const points = values.map((v, i) =>
                        `${i * (60 / (values.length - 1))},${18 - (v - min) / (max - min + 0.01) * 16}`
                    ).join(' ');
                    sparkline = `<svg class='sparkline'><polyline fill='none' stroke='#e961ab' stroke-width='2' points='${points}'/></svg>`;
                }

                return {
                    monthNum,
                    monthYear,
                    min,
                    max,
                    avg,
                    minDay,
                    maxDay,
                    trend,
                    trendValue,
                    trendPercent,
                    badge,
                    sparkline,
                    dataCount: detailData.length,
                    isCurrentPeriod: true,
                    totalConsumption,
                    monthlyCost
                };
            }

            // Kỳ đã qua: lấy dữ liệu theo chu kỳ thanh toán
            let monthDataArr;
            if (billingCycle.type === 'calendar' || (billingCycle.type === 'cycle' && billingCycle.startDay === 1)) {
                monthDataArr = this.dailyData.filter(d =>
                    d.Ngày && d.Ngày.slice(3, 10) === monthYear && d["Điện tiêu thụ (kWh)"] > 0
                );
            } else {
                monthDataArr = this.getDataByBillingPeriod(monthYear, billingCycle.startDay)
                    .filter(d => d["Điện tiêu thụ (kWh)"] > 0);
            }

            let min = 0, max = 0, avg = 0, minDay = '', maxDay = '';
            let trend = 'flat', trendValue = 0, trendPercent = 0, badge = '';
            let sparkline = '';
            let totalConsumption = 0, monthlyCost = 0;

            if (monthDataArr.length > 0) {
                const values = monthDataArr.map(d => d["Điện tiêu thụ (kWh)"]);
                min = Math.min(...values);
                max = Math.max(...values);
                avg = values.reduce((a, b) => a + b, 0) / values.length;
                totalConsumption = values.reduce((a, b) => a + b, 0);
                minDay = monthDataArr.find(d => d["Điện tiêu thụ (kWh)"] === min)?.Ngày || '';
                maxDay = monthDataArr.find(d => d["Điện tiêu thụ (kWh)"] === max)?.Ngày || '';

                // Tìm dữ liệu tiền điện từ monthlyData (theo cả Tháng và Năm)
                const [monthStr, yearStr] = monthYear.split('-');
                const targetYear = this.normalizeYearValue(yearStr);
                const monthlyDataItem = this.monthlyData?.TienDien?.find(item => {
                    const itemMonth = item.Tháng.toString().padStart(2, '0');
                    const itemYear = this.normalizeYearValue(item.Năm) || new Date().getFullYear();
                    const targetMonth = monthNum.toString().padStart(2, '0');
                    return itemMonth === targetMonth && itemYear === targetYear;
                });

                if (monthlyDataItem && monthlyDataItem["Tiền Điện"]) {
                    monthlyCost = parseInt(monthlyDataItem["Tiền Điện"] || 0);
                } else {
                    if (totalConsumption > 0) {
                        monthlyCost = null; // No issued bill: do not invent historical money.
                    } else {
                        monthlyCost = 0;
                    }
                }

                // Tính trend so với chu kỳ trước
                if (index < recentMonths.length - 1) {
                    const nextMonthYear = recentMonths[index + 1];
                    let prevArr;

                    if (billingCycle.type === 'calendar' || (billingCycle.type === 'cycle' && billingCycle.startDay === 1)) {
                        prevArr = this.dailyData.filter(d =>
                            d.Ngày && d.Ngày.slice(3, 10) === nextMonthYear && d["Điện tiêu thụ (kWh)"] > 0
                        );
                    } else {
                        prevArr = this.getDataByBillingPeriod(nextMonthYear, billingCycle.startDay)
                            .filter(d => d["Điện tiêu thụ (kWh)"] > 0);
                    }

                    const prevAvg = prevArr.length > 0 ?
                        prevArr.map(d => d["Điện tiêu thụ (kWh)"]).reduce((a, b) => a + b, 0) / prevArr.length : 0;

                    if (prevAvg > 0 && avg > 0) {
                        trendValue = avg - prevAvg;
                        trendPercent = (trendValue / prevAvg) * 100;

                        if (trendValue > 0.01) trend = 'up';
                        else if (trendValue < -0.01) trend = 'down';

                        // Badge nếu tăng/giảm mạnh
                        if (trendPercent > 20) badge = '<span class="trend-badge">Tăng mạnh</span>';
                        else if (trendPercent < -20) badge = '<span class="trend-badge">Giảm mạnh</span>';
                    }
                }

                // Tạo sparkline SVG
                const points = values.map((v, i) =>
                    `${i * (60 / (values.length - 1))},${18 - (v - min) / (max - min + 0.01) * 16}`
                ).join(' ');
                sparkline = `<svg class='sparkline'><polyline fill='none' stroke='#e961ab' stroke-width='2' points='${points}'/></svg>`;
            }

            // Closed months use billed production and amounts, never daily sums.
            const closedYear = this.normalizeYearValue(monthYear.split('-')[1]);
            const matchesBill = item => parseInt(item.Tháng,10) === parseInt(monthNum,10) && this.normalizeYearValue(item.Năm) === closedYear;
            const officialProduction = this.monthlyData?.SanLuong?.find(matchesBill);
            const officialMoney = this.monthlyData?.TienDien?.find(matchesBill);
            if (officialProduction) totalConsumption = Number(officialProduction["Điện tiêu thụ (KWh)"]);
            monthlyCost = officialMoney ? Number(officialMoney["Tiền Điện"]) : 0;
            return {
                monthNum,
                monthYear,
                min,
                max,
                avg,
                minDay,
                maxDay,
                trend,
                trendValue,
                trendPercent,
                badge,
                sparkline,
                dataCount: monthDataArr.length,
                isCurrentPeriod: false,
                hasOfficialBill: Boolean(officialMoney),
                totalConsumption,
                monthlyCost
            };
        });
    }

    // Tính tiền điện theo bậc thang (từ NPC utils.py)
    calculateCurrentPeriod() {
        const billingCycle = this.getBillingCycle();
        const today = new Date();

        // Tính chu kỳ hiện tại
        const currentPeriod = this.tinhngaydauky(billingCycle.startDay, today);

        // Lấy dữ liệu trong kỳ hiện tại (chỉ từ ngày đầu kỳ đến hôm nay) để đếm số ngày
        const currentPeriodData = this.dailyData.filter(day => {
            if (!day.Ngày) return false;
            const dayDate = new Date(day.Ngày.split('-').reverse().join('-'));
            return dayDate >= currentPeriod.start && dayDate <= today &&
                day["Điện tiêu thụ (kWh)"] > 0;
        });

        // Xác định tháng hiển thị
        let displayMonth, displayYear;
        if (billingCycle.type === 'calendar') {
            displayMonth = today.getMonth() + 1;
            displayYear = today.getFullYear();
        } else if (billingCycle.startDay === 1 && billingCycle.type === 'cycle') {
            displayMonth = today.getMonth() + 1;
            displayYear = today.getFullYear();
        } else {
            displayMonth = currentPeriod.end_ky.getMonth() + 1;
            displayYear = currentPeriod.end_ky.getFullYear();
        }

        // ƯU TIÊN: Lấy dữ liệu từ sensor API nếu có
        if (this.currentPeriodFromSensor && Number.isFinite(this.currentPeriodFromSensor.tieu_thu_ky_nay)) {
            const consumption = this.currentPeriodFromSensor.tieu_thu_ky_nay;
            const cost = this.currentPeriodFromSensor.tien_dien_ky_nay;
            const billCalculation = {details:{source:'EVN API'}};


            return {
                month: displayMonth,
                year: displayYear,
                consumption: Math.round(consumption * 100) / 100,
                cost: cost,
                days: currentPeriodData.length,
                isCurrentPeriod: true,
                period: {
                    start: currentPeriod.start,
                    end: currentPeriod.end_ky
                },
                details: billCalculation.details
            };
        }

        // Không có sensor data
        console.warn('⚠️ calculateCurrentPeriod: No sensor data available!');
        return null;
    }

    // Kiểm tra xem tháng có phải là kỳ hiện tại không
    isCurrentPeriodMonth(monthYear, index) {
        const billingCycle = this.getBillingCycle();
        const today = new Date();

        if (billingCycle.type === 'calendar') {
            // Tháng dương lịch: kiểm tra có phải tháng hiện tại không
            const currentMonthYear = `${(today.getMonth() + 1).toString().padStart(2, '0')}-${today.getFullYear()}`;
            return monthYear === currentMonthYear;
        } else if (billingCycle.type === 'cycle' && billingCycle.startDay === 1) {
            // Chu kỳ được cấu hình thủ công từ ngày 1: kiểm tra có phải tháng hiện tại không
            const currentMonthYear = `${(today.getMonth() + 1).toString().padStart(2, '0')}-${today.getFullYear()}`;
            return monthYear === currentMonthYear;
        } else {
            // Chu kỳ thanh toán tùy chỉnh: chỉ tháng đầu tiên là kỳ hiện tại
            return index === 0;
        }
    }

    // Lấy danh sách các năm có trong dữ liệu
    getAvailableYears() {
        const years = new Set();

        // Lấy từ monthly data
        if (this.monthlyData && this.monthlyData.SanLuong) {
            this.monthlyData.SanLuong.forEach(item => {
                if (item.Năm) {
                    const year = this.normalizeYearValue(item.Năm);
                    if (year !== null) {
                        years.add(year);
                    }
                }
            });
        }

        // Lấy từ daily data
        if (this.dailyData && Array.isArray(this.dailyData)) {
            this.dailyData.forEach(day => {
                if (day.Ngày) {
                    const year = parseInt(day.Ngày.split('-')[2]);
                    if (!isNaN(year)) {
                        years.add(year);
                    }
                }
            });
        }

        return Array.from(years).sort((a, b) => b - a);
    }

    // Lọc monthly data theo năm (luôn trả về 12 tháng)
    getFilteredMonthlyData(year) {
        const targetYear = this.normalizeYearValue(year);
        const aggregated = this.getMonthlyAggregation(targetYear);
        const consumptionMap = new Map();
        const costMap = new Map();

        aggregated.SanLuong.forEach(item => {
            if (!item) return;
            const month = parseInt(item.Tháng, 10);
            const yearValue = this.normalizeYearValue(item.Năm);
            if (!month || yearValue === null) return;
            const key = `${yearValue}-${month}`;
            consumptionMap.set(key, typeof item["Điện tiêu thụ (KWh)"] === 'number'
                ? item["Điện tiêu thụ (KWh)"]
                : parseFloat(item["Điện tiêu thụ (KWh)"]) || 0);
        });

        aggregated.TienDien.forEach(item => {
            if (!item) return;
            const month = parseInt(item.Tháng, 10);
            const yearValue = this.normalizeYearValue(item.Năm);
            if (!month || yearValue === null) return;
            const key = `${yearValue}-${month}`;
            costMap.set(key, typeof item["Tiền Điện"] === 'number'
                ? item["Tiền Điện"]
                : parseFloat(item["Tiền Điện"]) || 0);
        });

        const months = [];
        if (targetYear === null) {
            const currentPeriod = this.calculateCurrentPeriod();
            const today = new Date();
            const endMonth = currentPeriod ? currentPeriod.month : today.getMonth() + 1;
            const endYear = currentPeriod ? currentPeriod.year : today.getFullYear();

            for (let i = 11; i >= 0; i--) {
                const date = new Date(endYear, endMonth - 1 - i, 1);
                months.push({ month: date.getMonth() + 1, year: date.getFullYear() });
            }
        } else {
            for (let month = 1; month <= 12; month++) {
                months.push({ month, year: targetYear });
            }
        }

        const currentPeriod = this.calculateCurrentPeriod();
        const currentPeriodKey = currentPeriod ? `${currentPeriod.year}-${currentPeriod.month}` : null;

        const SanLuong = [];
        const TienDien = [];

        months.forEach(({ month, year: yearValue }) => {
            const key = `${yearValue}-${month}`;
            const consumption = currentPeriodKey === key
                ? currentPeriod.consumption
                : (consumptionMap.get(key) || 0);
            const cost = currentPeriodKey === key
                ? currentPeriod.cost
                : (costMap.get(key) || 0);

            SanLuong.push({
                Tháng: month,
                Năm: yearValue,
                "Điện tiêu thụ (KWh)": consumption
            });

            TienDien.push({
                Tháng: month,
                Năm: yearValue,
                "Tiền Điện": cost
            });
        });

        return { SanLuong, TienDien };
    }
}

// Export cho sử dụng global
window.DataManager = DataManager;
