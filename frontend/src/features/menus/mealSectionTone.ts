const MEAL_SECTION_TONE_COUNT=6

export function mealSectionTone(index:number){
  return `menu-meal-tone-${index%MEAL_SECTION_TONE_COUNT}`
}
