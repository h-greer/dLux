"""
dLux/spiders.py
---------------
A host of pre-implemented spider construction routines. 
"""
import abc 
import jax
import typing
import equinox
import functools
import dLux
import dLux.utils
import jax.numpy as np 
import matplotlib.pyplot as pyplot


Layer = typing.TypeVar("Layer")


class Spider(dLux.Base, abc.ABC):
    """
    An abstraction on the concept of an optical spider for a space telescope.
    These are the things that hold up the secondary mirrors. For example,

    Parameters
    ----------
    number_of_pixels: int
        The number of pixels along one edge of the image used to represent the 
        spider. 
    radius_of_spider: float, meters
        The physical width of the spider. For the moment it is assumed to be 
        embedded within a circular aperture.         
    width_of_image: float, meters
        The width of the image. If you wish to pad the array representation of
        the spider then set this to the padding factor multiplied by the 
        radius_of_spider parameter. 
    center_of_spicer: Array, meters 
        The [x, y] center of the spider.
    """  
    width_of_image: float
    number_of_pixels: int
    radius_of_spider: float
    centre_of_spider: float


    def __init__(
            self: Layer, 
            width_of_image: float,
            number_of_pixels: int, 
            radius_of_spider: float,
            centre_of_spider: float) -> Layer:
        """
        Parameters
        ----------
        number_of_pixels: int
            The number of pixels along one edge of the image used to represent 
            the spider. 
        radius_of_spider: float, meters
            The physical width of the spider. For the moment it is assumed to be 
            embedded within a circular aperture.         
        width_of_image: float, meters
            The width of the image. If you wish to pad the array representation of
            the spider then set this to the padding factor multiplied by the 
            radius_of_spider parameter. 
        center_of_spicer: Array, meters 
            The [x, y] center of the spider.
        """
        self.number_of_pixels = number_of_pixels
        self.width_of_image = np.asarray(width_of_image).astype(float)
        self.centre_of_spider = np.asarray(centre_of_spider).astype(float)
        self.radius_of_spider = np.asarray(radius_of_spider).astype(float)


    def _coordinates(self: Layer) -> float:
        """
        Generates a coordinate grid representing the positions of the pixels 
        relative to the centre of the spider. The representation that we 
        use is cartesian. 
    
        Returns 
        -------
        coordinates: float, meters
            The pixel coordinates.
        """
        pixel_scale = self.width_of_image / self.number_of_pixels
        pixel_centre = self.centre_of_spider / pixel_scale
        pixel_coordinates = dLux.utils.get_pixel_positions(
            self.number_of_pixels, pixel_centre[0], pixel_centre[1])
        return pixel_coordinates * pixel_scale  
 

    def _rotate(self: Layer, image: float, angle: float) -> float:
        """
        Rotate a set of coordinates by an amount angle. 
    
        Parameters
        ----------
        image: float, meters
            The physical coordinates for the pixel position as generated by 
            self._coordinates(). This should be a tensor with x then y along 
            the leading axis. 
        angle: float, radians
            The amount to rotate the coordinate system by. 

        Returns 
        -------
        coordinates: float, meters
            The rotate physical coordinate system. This will be a tensor with 
            x then y along the leading axis. 
        """
        coordinates = self._coordinates()
        rotation_matrix = np.array([
            [np.cos(angle), -np.sin(angle)], 
            [np.sin(angle), np.cos(angle)]])
        return np.apply_along_axis(np.matmul, 0, coordinates, rotation_matrix) 


    def _strut(self: Layer, angle: float, width: float) -> float:
        """
        Generates a representation of a single strut in the spider. This is 
        more complex than you might imagine since the strut can point in 
        any direction. 

        Parameters
        ----------
        angle: float, radians
            The angle that this strut points as measured from the positive 
            x-axis in radians. 
        width: float, meters
            The width of the strut in meters. Note: a large amount of effort 
            is made to make the edge soft so that autodiff does not achieve 
            infinite gradients and that means that in the output the exact 
            edge is not well defined.

        Returns
        -------
        strut: float
            The soft edged strut. 
        """
        coordinates = self._rotate(self._coordinates(), angle)
        distance = np.where(coordinates[0] > 0., np.abs(coordinates[1]), np.inf)
        spider = self._sigmoid(distance, width)
        return spider        

    
    # TODO: 
    def _sigmoid(self: Layer, distance: float, width: float) -> float:
        """
        The name is a misnomer but it has been kept for legacy reasons. 
        This is a routine that is used in the soft edging of the images. 
        
        Parameters
        ----------
        distance: float, meters
            A matrix representing the distance of each pixel from a point 
            line or otherwise a shape. Some useful hints for using this are 
            that setting regions to np.inf will convert them into exactly 1.
            i.e. inside a box. 
        width: float, meters
            This roughly represents the amount of soft edging. The best way to 
            use this parameter is by trying a few different values until you 
            find one that you like.

        Returns
        -------
        image: float 
            The soft edged image, taken from distance. 
        """
        steepness = self.number_of_pixels
        return (np.tanh(steepness * (distance - width)) + 1.) / 2.


    @abc.abstractmethod
    def _spider(self: Layer) -> float:
        """
        Represent the spider as an number_of_pixels by umber_of_pixels array. 

        Returns 
        -------
        spider: float
            The soft edged array representation of the spider. 
        """
        pass 

    
    @abc.abstractmethod
    def __call__(self: Layer, params: dict) -> dict:
        """
        Apply the spider to a wavefront. 

        Parameters
        ----------
        params: dict
            A dictionary of parameters that must contain a "Wavefront" entry.
        
        Returns 
        -------
        params: dict
            The same dictionary of parameter with an updated "Wavefront" entry.
        """
        pass 


class UniformSpider(Spider):
    """
    A spider with equally-spaced, equal-width struts. This is of course the 
    most common and simplest implementation of a spider. Gradients can be 
    taken with respect to the width of the struts and the global rotation 
    as well as the centre of the spider inherited from 

    Parameters
    ----------
    number_of_struts: int 
        The number of struts to equally space around the circle. This is not 
        a differentiable parameter. 
    width_of_struts: float, meters
        The width of each strut. 
    rotation: float, radians
        A global rotation to apply to the entire spider. 
    """
    number_of_struts: int
    width_of_struts: float
    rotation: float


    def __init__(
            self: Layer, 
            width_of_image: float,
            number_of_pixels: int, 
            radius_of_spider: float,
            centre_of_spider: float,
            number_of_struts: int, 
            width_of_struts: float, 
            rotation: float) -> Layer:
        """
        Parameters
        ----------
        number_of_pixels: int
            The number of pixels along one edge of the image used to represent 
            the spider. 
        radius_of_spider: float, meters
            The physical width of the spider. For the moment it is assumed to 
            be embedded within a circular aperture.         
        width_of_image: float, meters
            The width of the image. If you wish to pad the array representation 
            of the spider then set this to the padding factor multiplied by the 
            radius_of_spider parameter. 
        center_of_spicer: Array, meters 
            The [x, y] center of the spider.
        number_of_struts: int 
            The number of struts to equally space around the circle. This is not 
            a differentiable parameter. 
        width_of_struts: float, meters
            The width of each strut. 
        rotation: float, radians
            A global rotation to apply to the entire spider.
        """ 
        super().__init__(
            width_of_image, 
            number_of_pixels, 
            radius_of_spider,
            centre_of_spider)
        self.number_of_struts = number_of_struts
        self.rotation = np.asarray(rotation).astype(float)
        self.width_of_struts = np.asarray(width_of_struts).astype(float)


    @functools.partial(jax.vmap, in_axes=(None, 0, None))
    def _strut(self: Layer, angle: float, width: float) -> float:
        """
        A vectorised routine for constructing the struts. This has been done 
        to improve the performance of the program, and simply differs to 
        the super-class implementation. 

        Parameters
        ----------
        angle: float, radians
            The angle that this strut points as measured from the positive 
            x-axis in radians. 
        width: float, meters
            The width of the strut in meters.

        Returns
        -------
        strut: float
            The soft edged strut.
        """
        return super()._strut(angle, width)


    def _spider(self: Layer) -> float:
        """
        Represents the spider in a square array. Each strut is placed equally 
        around the circumference like a wll cut pizza. All the struts have the
        same width and a global rotation.
    
        Returns
        -------
        spider: float
            The array representation of the spider. 
        """
        angles = np.linspace(0, 2 * np.pi, self.number_of_struts, 
            endpoint=False)
        angles += self.rotation

        struts = self._strut(angles, self.width_of_struts)
        spider = np.prod(struts, axis=0)

        coordinates = self._coordinates()
        radial_coordinates = np.hypot(coordinates[0], coordinates[1])

        radial_distance = np.abs(radial_coordinates - self.radius_of_spider)\
            .at[radial_coordinates > self.radius_of_spider]\
            .set(-np.inf)

        soft_edge = self.width_of_image / self.number_of_pixels
        radial_soft_edge = self._sigmoid(radial_distance, soft_edge)

        return radial_soft_edge * spider
        
 
    def __call__(self: Layer, params: dict) -> dict:
        """
        Apply the spider to a wavefront, as it propagates through the spider. 

        Parameters
        ----------
        params: dict
            A dictionary of parameters that contains a "Wavefront" key. 

        Returns 
        -------
        params: dict 
            The same dictionary with the "Wavefront" value updated.
        """
        aperture = self._spider()
        wavefront = params["Wavefront"]
        wavefront = wavefront\
            .set_amplitude(wavefront.get_amplitude() * aperture)\
            .set_phase(wavefront.get_phase() * aperture)
        params["Wavefront"] = wavefront
        return params
