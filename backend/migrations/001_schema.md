# 001 初始表结构

应用首次启动以 SQLAlchemy 模型创建表与唯一约束。现有数据表只补建缺失表，升级到修改过字段的版本需要显式迁移。

- `users` 账号角色和加盐密码摘要。
- `datasets` 不可变记录批次，以名称和 SHA-256 去重。
- `package_corrections` 整包实耗的追加式更正：并发提交各自成行、互不覆盖，最新一笔参与重新归组后的计算。
- `runs` 记录参数、数据批次、运行租约、分析结果、导出文件及复核决定；`data_fingerprint` 保存运行时的数据指纹，源数据或更正变化后用于标记旧结果失效。
- `schedules` 保存定时计划和下一到期时间。
- `deliveries` 保存站内分发回执，每次运行最多一个回执。
- `audit_events` 记录登录、数据入库、整包更正、运行、复核和报表分发动作。

## 整包口径升级（002）

新增整包实耗工作流：CSV 增加可空列 `package_id`、`package_actual_minutes`；已存在的库需要：

```sql
CREATE TABLE package_corrections (
  id INTEGER PRIMARY KEY AUTO_INCREMENT,
  dataset_id INTEGER NOT NULL,
  package_id VARCHAR(60) NOT NULL,
  actual_minutes FLOAT NOT NULL,
  reason VARCHAR(500) NOT NULL,
  author VARCHAR(64) NOT NULL,
  created_at DATETIME NOT NULL,
  INDEX ix_package_corrections_dataset_id (dataset_id),
  INDEX ix_package_corrections_package_id (package_id),
  INDEX ix_package_corrections_created_at (created_at)
);
ALTER TABLE runs ADD COLUMN data_fingerprint VARCHAR(64) NULL;
```

全新环境由 `Base.metadata.create_all` 直接建出，无需手工执行。
