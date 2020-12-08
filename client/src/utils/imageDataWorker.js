import registerWebworker from 'webworker-promise/lib/register'


registerWebworker(async function (input) {
  if (input.operation === 'readImage') {
    return readImage(input)
  } else if (input.operation === 'writeImage') {
    return writeImage(input)
  } else if (input.operation === 'readDICOMImageSeries') {
    return readDICOMImageSeries(input)
  } else {
    throw new Error('Unknown worker operation')
  }
})