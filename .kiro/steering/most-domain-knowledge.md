# MOST Domain Knowledge & Rules

## MiniMOST Sequence Model

### Core Principles
- **Time Measurement Units (TMU)**: 1 TMU = 0.036 seconds, fundamental unit for all calculations
- **Seven-Position Format**: A/B/G/P/M/X/I sequence representing complete work motions
- **Single Authority Principle**: Backend engine is the only source of TMU calculations
- **Version Integrity**: All calculations must reference specific rule-set version for audit trail

### Sequence Structure
- **A (Action Distance)**: Reach/move distances in categories 1-3
- **B (Body Motion)**: Bend/arise motions with different effort levels  
- **G (Gain Control)**: Object acquisition with complexity factors
- **P (Position)**: Object placement with precision requirements
- **M (Manual Cranking)**: Rotational motions with resistance levels
- **X (Index)**: Small adjustment motions
- **I (Eye Time)**: Visual inspection and decision time

### Validation Rules
- **SIMO Constraints**: Simultaneous Motion rules must be respected
- **Value Ranges**: Each position has defined valid ranges per rule-set
- **Sequence Logic**: Motion sequences must make ergonomic sense
- **Narrative Quality**: Work instructions should be clear in both languages

## Level System (R1-R9)

### Hierarchy Rules
- **Main Level**: Primary work elements, foundational operations
- **Sub Level**: Supporting activities under main operations  
- **Cub Level**: Detail elements nested within sub operations
- **NB (Non-Basic)**: Elements that don't fit standard hierarchy

### Level Relationships
- **Nesting Depth**: sub⊃cub relationships enforced by business logic
- **Variable Levels**: Support for `~` (flexible) and `/` (alternative) notations
- **Order Constraints**: Sequence numbering must respect hierarchy rules
- **Content Validation**: Each level must have appropriate content type

### R1-R9 Validation
- **R1**: Main level content requirements
- **R2**: Sub level nesting rules
- **R3**: Cub level depth constraints
- **R4-R9**: Advanced relationship and dependency rules

## Line Balancing Integration

### Export Requirements
- **JSON Format**: Standardized structure for LB system consumption
- **Node Relationships**: Proper precedence and dependency mapping
- **Timing Data**: Accurate TMU calculations with variance factors
- **Level Hierarchy**: Preserved main/sub/cub structure for analysis

### Data Integrity
- **Snapshot Consistency**: Exported data matches worksheet state exactly
- **Version Tracking**: Clear linkage to rule-set version used
- **Audit Trail**: Complete history of changes and calculations
- **Validation Gates**: Pre-export validation of all calculations

## Rule-Set Management

### Versioning Strategy
- **Draft → Published → Retired**: Clear lifecycle management
- **Immutable Published**: No changes allowed after publication
- **Backward Compatibility**: Old worksheets maintain original calculations
- **Migration Support**: Clear upgrade paths between rule-set versions

### Business Rules
- **IE Authorization**: Only Industrial Engineers can modify rule-sets
- **Validation Required**: All changes must pass golden test vectors
- **Documentation**: Changes require clear business justification
- **Rollback Support**: Ability to revert to previous versions if needed

## Quality Assurance

### Golden Test Vectors
- **GM28/CM29**: Standard reference calculations that must always pass
- **Educational Examples**: Seven teaching cases from official documentation  
- **Edge Cases**: Boundary conditions and error scenarios
- **Regression Prevention**: Any engine changes must maintain all golden values

### Validation Process
- **Multi-layer Validation**: Schema, business rules, and domain constraints
- **Real-time Feedback**: Immediate validation during data entry
- **Batch Validation**: Comprehensive checks for bulk operations
- **Error Reporting**: Clear, actionable error messages for users

### Performance Standards
- **Calculation Speed**: TMU calculations must complete within acceptable time
- **Concurrency**: Support multiple users calculating simultaneously
- **Accuracy**: Floating-point precision handled consistently
- **Scalability**: Performance maintained as data volumes grow

## Industrial Engineering Context

### MOST Methodology
- **Maynard Operation Sequence Technique**: Standard work measurement approach
- **Predetermined Motion Time**: Scientific basis for time standards
- **Process Analysis**: Understanding work flow and optimization opportunities
- **Ergonomic Considerations**: Motion economy and worker safety factors

### Compliance Requirements
- **Audit Standards**: Full traceability of time study data
- **Version Control**: Complete history of changes and approvals
- **Role-Based Access**: Appropriate permissions for different user types
- **Data Retention**: Long-term storage for historical analysis